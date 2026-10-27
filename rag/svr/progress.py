"""Roll-up of task progress into the document, and the reconciler for stranded tasks (plan 04-12; ING-08, DOC-12, D-06, D-14, R-157).

Only the holder of the Valkey lock ``update_progress`` runs a cycle. A cycle looks at every document with ``run == "1"`` and decides, in one
place: still running (write the mean progress and the merged lines), finished (every task done, at least one chunk), failed at the first failed task,
or failed ``no_readable_text`` (every task done, zero chunks). The transition runs in one transaction with the document row locked and ``run`` read
again, so a cancel that landed meanwhile wins. A document at ``run == "2"`` is never selected.
"""

from __future__ import annotations

import datetime
import logging
import re
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from api.db.database import DB, transaction
from api.db.models import Document, Knowledgebase, PipelineOperationLog
from api.db.models.base import current_timestamp_ms, timestamp_to_date
from api.db.services import task_service
from api.db.services.service_errors import ServiceError
from api.db.services.task_service import MAX_PROGRESS_LINES
from api.db.services.totals_service import settle_totals
from common.doc_store.doc_store_base import DocStoreConnection, DocStoreError, index_name
from common.ingest_codes import LOG_DONE, LOG_FAILED, LOG_RUNNING, PLAIN_MESSAGES, RUN_DONE, RUN_FAILED, RUN_RUNNING, is_terminal
from common.log_utils import redact_text
from common.settings import Settings
from rag.queue.queue_base import TaskQueue
from rag.svr.failure import FailureInfo, parse_failure_line
from rag.svr.task_lock import TaskLock, open_client
from rag.utils.es_conn import get_doc_store

logger = logging.getLogger(__name__)

LOCK_NAME = "update_progress"
LOCK_TTL_SECONDS = 10
RECONCILE_EVERY_SECONDS = 30
RECONCILE_LIMIT = 100

_MACHINE = re.compile(r"^(?:\d\d:\d\d:\d\d\s+)?\[(?:pages|skipped|layout)\]\s")
_PAGES = re.compile(r"\[pages\]\s+total=(\d+)\s+without_text=(\d+)")
_SKIPPED = re.compile(r"\[skipped\]\s+images=(\d+)")
_LAYOUT = re.compile(r"\[layout\]\s+backend=(deepdoc-onnx)\s+regions=(\d+)")
_STAMP = re.compile(r"^(\d\d:\d\d:\d\d)\s")


@dataclass
class RollupStats:
    documents: int = 0
    finished: int = 0
    failed: int = 0
    skipped: int = 0


@dataclass(frozen=True)
class _Doc:
    id: str
    dataset_id: str
    tenant_id: str
    began: datetime.datetime | None


@dataclass(frozen=True)
class _Summary:
    progress: float
    lines: list[str]
    attempts: int
    pages_total: int
    pages_without_text: int
    images_skipped: int
    first_failed: Any
    all_done: bool
    layout_backend: str | None = None
    layout_regions: int = 0


def _running_documents(doc_ids: Sequence[str] | None) -> list[_Doc]:
    with DB.connection_context():
        query = Document.select(Document.id, Document.kb_id, Document.process_begin_at, Knowledgebase.tenant_id).join(
            Knowledgebase, on=(Document.kb_id == Knowledgebase.id)
        ).where(Document.run == RUN_RUNNING)
        if doc_ids is not None:
            query = query.where(Document.id.in_(list(doc_ids)))
        return [_Doc(r.id, r.kb_id, r.knowledgebase.tenant_id, r.process_begin_at) for r in query]


def _last_match(pattern: re.Pattern[str], text: str) -> re.Match[str] | None:
    found = None
    for line in text.splitlines():
        match = pattern.search(line)
        if match:
            found = match
    return found


def _merge_lines(tasks: Sequence[Any]) -> list[str]:
    lines = [line for t in tasks for line in (t.progress_msg or "").splitlines() if line.strip() and not _MACHINE.match(line.strip())]
    if len(tasks) > 1:
        lines = [line for _, line in sorted(enumerate(lines), key=lambda p: ((_STAMP.match(p[1]).group(1) if _STAMP.match(p[1]) else ""), p[0]))]
    return [redact_text(line) for line in lines[-MAX_PROGRESS_LINES:]]


def _summarise(tasks: Sequence[Any]) -> _Summary:
    pages_total = pages_without = skipped = layout_regions = 0
    layout_backend = None
    for task in tasks:
        text = task.progress_msg or ""
        pages = _last_match(_PAGES, text)
        if pages:
            pages_total += int(pages.group(1))
            pages_without += int(pages.group(2))
        layout = _last_match(_LAYOUT, text)
        if layout:
            layout_backend = layout.group(1)
            layout_regions += int(layout.group(2))
        images = _last_match(_SKIPPED, text)
        if images:
            skipped += int(images.group(1))
    progress = sum(min(max(float(t.progress or 0), 0.0), 1.0) for t in tasks) / len(tasks)
    failed = next((t for t in tasks if (t.progress or 0) < 0), None)
    return _Summary(
        progress=progress,
        lines=_merge_lines(tasks),
        attempts=max(int(t.retry_count or 0) for t in tasks),
        pages_total=pages_total,
        pages_without_text=pages_without,
        images_skipped=skipped,
        first_failed=failed,
        all_done=all((t.progress or 0) >= 1 for t in tasks),
        layout_backend=layout_backend, layout_regions=layout_regions,
    )


def _stamp() -> dict[str, Any]:
    now = current_timestamp_ms()
    return {"update_time": now, "update_date": timestamp_to_date(now)}


def _duration(doc: _Doc) -> float:
    return max((datetime.datetime.now() - doc.began).total_seconds(), 0.001) if doc.began else 0.0


def _write_running(doc: _Doc, summary: _Summary) -> None:
    text = "\n".join(summary.lines)
    with DB.connection_context():
        Document.update(progress=summary.progress, progress_msg=text, **_stamp()).where((Document.id == doc.id) & (Document.run == RUN_RUNNING)).execute()
        _update_log(doc.id, progress=summary.progress, progress_msg=text)


def _update_log(doc_id: str, *, dsl: dict[str, Any] | None = None, status: str | None = None, **values: Any) -> None:
    row = PipelineOperationLog.select().where((PipelineOperationLog.document_id == doc_id) & (PipelineOperationLog.operation_status == LOG_RUNNING)).order_by(
        PipelineOperationLog.create_time.desc()
    ).first()
    if row is None:
        return
    if dsl is not None:
        values["dsl"] = {**dict(row.dsl or {}), **dsl}
    if status is not None:
        values["operation_status"] = status
    PipelineOperationLog.update(**values, **_stamp()).where(PipelineOperationLog.id == row.id).execute()


def _transition(doc: _Doc, run: str, progress: float, text: str, *, log_status: str, log_text: str, dsl: dict[str, Any], store: DocStoreConnection) -> bool:
    """Set the final state and close the log row in one transaction under a row lock.

    False when the document is no longer running (a cancel won). Both writes commit together, so a reader never sees a
    finished document whose log row still says running, and a failed log write leaves the document running for the next cycle.
    """
    with DB.connection_context(), transaction():
        row = Document.select(Document.run, Document.status).where(Document.id == doc.id).for_update().first()
        if row is None or row.run != RUN_RUNNING:
            return False
        # Serialize with document switching and acknowledge the index update before publishing completion.
        if not store.update({"doc_id": [doc.id]}, {"doc_enabled_int": 1 if (row.status or "1") == "1" else 0}, index_name(doc.tenant_id), doc.dataset_id):
            raise DocStoreError("document switch synchronization failed")
        duration = _duration(doc)
        Document.update(run=run, progress=progress, progress_msg=text, process_duration=duration, **_stamp()).where(Document.id == doc.id).execute()
        _update_log(doc.id, status=log_status, progress=progress, progress_msg=log_text, process_duration=duration, dsl=dsl)
    return True


def _failure_error(failed: Any | None) -> FailureInfo:
    info = parse_failure_line(failed.progress_msg) if failed is not None else None
    return info or FailureInfo("parse", "unexpected", PLAIN_MESSAGES["unexpected"])


def _settle(settings: Settings, doc: _Doc, store: DocStoreConnection) -> int | None:
    try:
        return settle_totals(settings, doc.tenant_id, doc.dataset_id, doc.id, doc_store=store)[0]
    except ServiceError:
        logger.warning("roll-up could not settle totals", extra={"document": doc.id})
        return None


def _error_dsl(info: FailureInfo, attempts: int, max_attempts: int) -> dict[str, Any]:
    error: dict[str, Any] = {"step": info.step, "code": info.code, "message": info.message}
    if info.detail:
        error["detail"] = info.detail
    return {"error": error, "attempts": attempts, "retried": (not is_terminal(info.code)) and attempts >= max_attempts}


def _counts_dsl(summary: _Summary, chunks: int) -> dict[str, Any]:
    return {
        **({"layout_backend": summary.layout_backend, "layout_regions": summary.layout_regions} if summary.layout_backend else {}),
        "chunks": chunks,
        "pages_total": summary.pages_total,
        "pages_without_text": summary.pages_without_text,
        "images_skipped": summary.images_skipped,
    }


def _finish(settings: Settings, doc: _Doc, summary: _Summary, store: DocStoreConnection, stats: RollupStats) -> None:
    text = "\n".join(summary.lines)
    max_attempts = settings.ingest.max_attempts
    if summary.first_failed is not None:
        failed = summary.first_failed
        info = _failure_error(failed)
        chunks = _settle(settings, doc, store)
        dsl = {**_error_dsl(info, int(failed.retry_count or 0), max_attempts), **_counts_dsl(summary, chunks or 0)}
        if not _transition(doc, RUN_FAILED, -1.0, text, log_status=LOG_FAILED, log_text=text, dsl=dsl, store=store):
            return
        stats.failed += 1
        return
    chunks = _settle(settings, doc, store)
    if chunks is None:
        return  # the index is unreachable: decide next cycle
    if chunks == 0:
        info = FailureInfo("parse", "no_readable_text", PLAIN_MESSAGES["no_readable_text"])
        line = f"[failed] step={info.step} code={info.code} message={info.message}"
        dsl = {**_error_dsl(info, summary.attempts, max_attempts), **_counts_dsl(summary, 0)}
        if not _transition(doc, RUN_FAILED, -1.0, f"{text}\n{line}" if text else line, log_status=LOG_FAILED, log_text=text, dsl=dsl, store=store):
            return
        stats.failed += 1
        return
    dsl = {"attempts": summary.attempts, **_counts_dsl(summary, chunks)}
    if not _transition(doc, RUN_DONE, 1.0, text, log_status=LOG_DONE, log_text=text, dsl=dsl, store=store):
        return
    stats.finished += 1


def _roll_document(settings: Settings, doc: _Doc, store: DocStoreConnection, stats: RollupStats) -> None:
    tasks = task_service.tasks_of(doc.id)
    if not tasks:
        stats.skipped += 1
        return
    stats.documents += 1
    summary = _summarise(tasks)
    if summary.first_failed is not None or summary.all_done:
        _finish(settings, doc, summary, store, stats)
    else:
        _write_running(doc, summary)


def rollup_once(settings: Settings, *, doc_store: DocStoreConnection | None = None, doc_ids: Sequence[str] | None = None) -> RollupStats:
    """One pass over the running documents (or only ``doc_ids``). A failure on one document is logged and does not stop the others."""
    stats = RollupStats()
    store = doc_store if doc_store is not None else get_doc_store(settings)
    for doc in _running_documents(doc_ids):
        try:
            _roll_document(settings, doc, store, stats)
        except Exception as exc:  # noqa: BLE001 - one document's trouble never stops the cycle; progress writes are not retried (R-83)
            logger.warning("roll-up failed for a document", extra={"document": doc.id, "error_type": type(exc).__name__})
    return stats


def reconcile_once(settings: Settings, queue: TaskQueue) -> int:
    """Publish again every unfinished task of a running document that has no lock and has not changed for ``reconcile_after_seconds`` (R-157)."""
    ingest = settings.ingest
    stale = task_service.unfinished_tasks_for_reconcile(ingest.reconcile_after_seconds * 1000, RECONCILE_LIMIT)
    if not stale:
        return 0
    client = open_client(settings)
    published = 0
    try:
        for task_id, digest in stale:
            if TaskLock.exists(client, ingest.queue_prefix, task_id):
                continue
            queue.enqueue(task_id, digest, 0)
            task_service.touch_task(task_id)
            published += 1
            logger.info("reconciler published a stranded task", extra={"task": task_id})
    finally:
        client.close()
    return published


class RollUpDaemon(threading.Thread):
    def __init__(self, settings: Settings, queue: TaskQueue, stop_event: threading.Event, *, doc_store: DocStoreConnection | None = None) -> None:
        super().__init__(name="rollup", daemon=True)
        self._settings = settings
        self._queue = queue
        self._stop_event = stop_event
        self._doc_store = doc_store
        self._client = open_client(settings)

    def cycle(self, reconcile: bool = False) -> RollupStats | None:
        """One guarded pass; None when another process holds ``update_progress``."""
        lock = TaskLock.named(self._client, self._settings.ingest.queue_prefix, LOCK_NAME, LOCK_TTL_SECONDS)
        if not lock.acquire():
            return None
        try:
            stats = rollup_once(self._settings, doc_store=self._doc_store)
            if reconcile:
                reconcile_once(self._settings, self._queue)
            return stats
        finally:
            lock.release()

    def run(self) -> None:
        next_reconcile = time.monotonic() + RECONCILE_EVERY_SECONDS
        while not self._stop_event.wait(self._settings.ingest.progress_interval_seconds):
            due = time.monotonic() >= next_reconcile
            try:
                self.cycle(reconcile=due)
                if due:
                    next_reconcile = time.monotonic() + RECONCILE_EVERY_SECONDS
            except Exception as exc:  # noqa: BLE001 - an outage never ends the daemon
                logger.warning("roll-up cycle failed", extra={"error_type": type(exc).__name__})
        self._client.close()
