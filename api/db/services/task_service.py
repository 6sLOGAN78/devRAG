"""Task rows for ingestion: page-range split, digest, attempt counter and progress writers (plan 04-10; ING-01, ING-11, D-05, R-158).

One ``task`` row is one slice of one document: a PDF is cut into ranges of ``ingest.task_page_size`` pages, everything else is a single row that
covers ``0..MAXIMUM_TASK_PAGE_NUMBER``. Ranges are 0-based and exclusive at the end. Every writer here stamps ``update_time`` by hand because
``Model.update(...).execute()`` does not (only ``save()`` does). The module imports no web framework and writes no message to a client.
"""

from __future__ import annotations

import datetime
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import peewee
import xxhash

from api.db.database import DB, transaction
from api.db.models import Document, Knowledgebase, Task
from api.db.models.base import current_timestamp_ms, timestamp_to_date
from api.db.models.knowledge import MAXIMUM_TASK_PAGE_NUMBER
from common.log_utils import redact_text

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "1"
MAX_PROGRESS_LINES = 3000
MAX_PROGRESS_LINE_CHARS = 2000
_BELOW_ONE = 0.999999

CLAIMED = "claimed"
EXHAUSTED = "exhausted"
FINISHED = "finished"
GONE = "gone"


@dataclass(frozen=True)
class Claim:
    outcome: str
    attempt: int = 0


@dataclass(frozen=True)
class TaskContext:
    task_id: str
    doc_id: str
    dataset_id: str
    tenant_id: str
    from_page: int
    to_page: int
    digest: str
    retry_count: int
    doc_name: str
    doc_suffix: str
    doc_location: str
    doc_size: int
    doc_run: str
    doc_status: str
    content_hash: str
    parser_id: str
    parser_config: dict[str, Any]
    embd_id: str
    created_by: str


def split_pages(total_pages: int | None, page_size: int) -> list[tuple[int, int]]:
    """0-based, end-exclusive page ranges. Unknown or zero page counts (and every non-PDF file) give one range over the whole file."""
    if not total_pages or total_pages <= 0 or page_size <= 0:
        return [(0, MAXIMUM_TASK_PAGE_NUMBER)]
    return [(start, min(start + page_size, total_pages)) for start in range(0, total_pages, page_size)]


def task_digest(
    doc_id: str,
    from_page: int,
    to_page: int,
    content_hash: str,
    parser_id: str,
    chunk_token_num: int,
    delimiter: str,
    overlapped_percent: int | float,
) -> str:
    """16 hex characters (xxh64) that change when any input that decides the chunks changes."""
    parts = (doc_id, from_page, to_page, content_hash, parser_id, chunk_token_num, delimiter, overlapped_percent, PIPELINE_VERSION)
    return xxhash.xxh64("\x1f".join(str(p) for p in parts).encode("utf-8")).hexdigest()


def _stamp() -> dict[str, Any]:
    now = current_timestamp_ms()
    return {"update_time": now, "update_date": timestamp_to_date(now)}


def load_task_context(task_id: str) -> TaskContext | None:
    """Task, document and dataset in one query; None when any of the three rows is gone."""
    with DB.connection_context():
        row = (
            Task.select(Task, Document, Knowledgebase)
            .join(Document, on=(Task.doc_id == Document.id))
            .join(Knowledgebase, on=(Document.kb_id == Knowledgebase.id))
            .where(Task.id == task_id)
            .first()
        )
        if row is None:
            return None
        task, doc = row, row.document
        kb = doc.knowledgebase
    return TaskContext(
        task_id=task.id,
        doc_id=doc.id,
        dataset_id=kb.id,
        tenant_id=kb.tenant_id,
        from_page=int(task.from_page or 0),
        to_page=int(task.to_page if task.to_page is not None else MAXIMUM_TASK_PAGE_NUMBER),
        digest=task.digest or "",
        retry_count=int(task.retry_count or 0),
        doc_name=doc.name or "",
        doc_suffix=doc.suffix or "",
        doc_location=doc.location or "",
        doc_size=int(doc.size or 0),
        doc_run=doc.run or "0",
        doc_status=doc.status or "1",
        content_hash=doc.content_hash or "",
        parser_id=doc.parser_id,
        parser_config=dict(doc.parser_config or {}),
        embd_id=kb.embd_id,
        created_by=doc.created_by,
    )


@dataclass(frozen=True)
class DocSwitch:
    enabled: bool
    run: str


def document_switch(doc_id: str) -> DocSwitch | None:
    """The document's current search switch (``status``) and run state, read fresh; None when the document is gone."""
    with DB.connection_context():
        row = Document.select(Document.status, Document.run).where(Document.id == doc_id).first()
    if row is None:
        return None
    return DocSwitch(enabled=(row.status or "1") == "1", run=row.run or "0")


def store_thumbnail(doc_id: str, data_url: str) -> bool:
    """Write the thumbnail only when the document has none (the first task wins). True when written."""
    with DB.connection_context():
        changed = Document.update(thumbnail=data_url, **_stamp()).where((Document.id == doc_id) & ((Document.thumbnail.is_null()) | (Document.thumbnail == ""))).execute()
    return bool(changed)


def has_thumbnail(doc_id: str) -> bool:
    with DB.connection_context():
        row = Document.select(Document.thumbnail).where(Document.id == doc_id).first()
    return bool(row and row.thumbnail)


def claim_attempt(task_id: str, cap: int) -> Claim:
    """Count one attempt, atomically and only while the task is unfinished and below ``cap``.

    The guard is in the UPDATE itself, so two workers handed the same task cannot both go over the cap. When no row changed the row is read
    again to say why: ``exhausted`` (attempts used up), ``finished`` (done or failed) or ``gone`` (deleted).
    """
    now = datetime.datetime.now()
    with DB.connection_context():
        changed = (
            Task.update(retry_count=Task.retry_count + 1, begin_at=peewee.fn.COALESCE(Task.begin_at, now), **_stamp())
            .where((Task.id == task_id) & (Task.progress >= 0) & (Task.progress < 1) & (Task.retry_count < cap))
            .execute()
        )
        row = Task.select(Task.retry_count, Task.progress).where(Task.id == task_id).first()
    if row is None:
        return Claim(GONE)
    if changed:
        return Claim(CLAIMED, int(row.retry_count))
    if row.progress is not None and (row.progress >= 1 or row.progress < 0):
        return Claim(FINISHED)
    return Claim(EXHAUSTED, int(row.retry_count or 0))


def refund_attempt(task_id: str) -> None:
    """Give back one attempt (a delivery that did no work, such as a lost lock). Never below zero."""
    with DB.connection_context():
        Task.update(retry_count=peewee.fn.GREATEST(Task.retry_count - 1, 0), **_stamp()).where(Task.id == task_id).execute()


def _plain_line(line: str) -> str:
    text = redact_text(" ".join(str(line).split()))
    return text[:MAX_PROGRESS_LINE_CHARS]


def _stamped_line(line: str) -> str:
    return f"{datetime.datetime.now().strftime('%H:%M:%S')}  {_plain_line(line)}"


def _append_message(existing: str | None, line: str) -> str:
    lines = (existing or "").splitlines()
    lines.append(_stamped_line(line))
    return "\n".join(lines[-MAX_PROGRESS_LINES:])


def _write_message(task_id: str, line: str, values: dict[str, Any]) -> None:
    with DB.connection_context(), transaction():
        row = Task.select(Task.progress_msg).where(Task.id == task_id).for_update().first()
        if row is None:
            return
        Task.update(progress_msg=_append_message(row.progress_msg, line), **values, **_stamp()).where(Task.id == task_id).execute()


def set_progress(task_id: str, progress: float, line: str) -> None:
    """Append one redacted line (the last 3000 are kept) and write ``progress`` clamped to ``[0, 1)``."""
    value = min(max(float(progress), 0.0), _BELOW_ONE)
    _write_message(task_id, line, {"progress": value})


def mark_task_done(task_id: str, chunk_ids: Sequence[str], duration_seconds: float) -> None:
    """``progress = 1``, the chunk id manifest (space separated) and the duration, in one UPDATE."""
    with DB.connection_context():
        Task.update(progress=1.0, chunk_ids=" ".join(chunk_ids), process_duration=float(duration_seconds), **_stamp()).where(Task.id == task_id).execute()


def mark_task_failed(task_id: str, line: str) -> None:
    """``progress = -1`` and the failure line appended."""
    _write_message(task_id, line, {"progress": -1.0})


def task_is_current(task_id: str) -> bool:
    """True while the task row still exists (a re-parse or a delete replaces it)."""
    with DB.connection_context():
        return Task.select(Task.id).where(Task.id == task_id).first() is not None


def tasks_of(doc_id: str) -> list[Task]:
    with DB.connection_context():
        return list(Task.select().where(Task.doc_id == doc_id).order_by(Task.from_page))
