"""Start, cancel and re-parse a document: the state transitions behind the parse button (plan 04-10; ING-01, ING-12, DOC-09..11, D-01..D-04, D-06, D-09).

Nothing parses at upload; parsing starts only through :func:`start_parse`. The order is fixed so a refused request changes nothing:

1. ``authorize_parse`` (visibility first, then ``datasets.manage_document``).
2. Every id is checked before any state changes: it is in the dataset (one ``NOT_FOUND``), the caller may change it (uploader, dataset creator,
   owner or admin, judged on the permission subject so an API token is never elevated), its type can be parsed, its chunking method is built, the
   dataset's embedding model is still in the workspace, it is not already running.
3. The confirmation rule: a request that would replace chunks is ``409 confirm_required`` with the documents and their counts, unless
   ``confirm_replace``. All or nothing: one document that needs confirmation stops the whole request.
4. The queue answers a ping. PDF page counts are read. Only then does anything change: under the dataset lock the chunks of the documents that
   have any are deleted from the index, and one transaction replaces task rows, writes the log row and resets the documents. After the commit one
   message per task is published; if that fails the documents are set to failed with code ``queue_unavailable`` and the answer is 503.

The module imports no web framework. Error messages are fixed text; infrastructure errors are logged by class name only.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from collections.abc import Sequence
from contextlib import ExitStack
from dataclasses import dataclass

import peewee

from api.apps.permissions_gen import allowed
from api.db.database import DB, transaction
from api.db.models import Document, Knowledgebase, PipelineOperationLog, Task
from api.db.models.base import current_timestamp_ms, timestamp_to_date
from api.db.services import task_service
from api.db.services.auth_service import Principal
from api.db.services.document_service import AREA, DEADLOCK_ATTEMPTS, LOCK_TIMEOUT_SECONDS, MANAGE_DOCUMENT, _clean_ids
from api.db.services.knowledgebase_service import DatasetRecord, VisibleDataset, _named_lock, embedding_dimensions, load_visible_dataset, upload_lock_name
from api.db.services.pdf_pages import pdf_page_count
from api.db.services.service_errors import Kind, ServiceError
from api.db.services.tenant_scope import can_remove_document
from api.db.services.totals_service import settle_totals
from api.utils import reasons
from common.doc_store.doc_store_base import DocStoreConnection, DocStoreError, index_name
from common.ingest_codes import LOG_CANCELLED, LOG_FAILED, LOG_RUNNING, RUN_CANCELLED, RUN_DONE, RUN_FAILED, RUN_NOT_STARTED, RUN_RUNNING
from common.ratelimit import FixedWindowLimiter, RateLimited, RateLimitUnavailable
from common.settings import Settings
from rag.chunking.factory import available as chunker_available
from rag.parsers.router import parseable
from rag.queue.factory import get_queue
from rag.queue.queue_base import QueueUnavailable, TaskQueue
from rag.utils.es_conn import get_doc_store
from rag.utils.storage_base import Storage
from rag.utils.storage_factory import get_storage

logger = logging.getLogger(__name__)

MAX_PARSE_IDS = 100
_MYSQL_DEADLOCK = 1213
_TASK_TYPE = "parse"
_SOURCE_LOCAL = "local"
_DEFAULT_CHUNK_TOKENS = 512
_DEFAULT_DELIMITER = "\n"


@dataclass(frozen=True)
class ParseStarted:
    doc_id: str
    task_count: int


@dataclass(frozen=True)
class ChunkCounts:
    chunk_count: int = 0
    edited_count: int = 0
    manual_count: int = 0


def _not_found() -> ServiceError:
    return ServiceError(Kind.NOT_FOUND, reasons.DATASET_NOT_FOUND, "not found")


def _index_unavailable() -> ServiceError:
    return ServiceError(Kind.UNAVAILABLE, reasons.INDEX_UNAVAILABLE, "the search index is not available, try again shortly")


def _queue_unavailable() -> ServiceError:
    return ServiceError(Kind.UNAVAILABLE, reasons.QUEUE_UNAVAILABLE, "the task queue is not available, try again shortly")


def parse_rate_guard(settings: Settings, tenant_id: str, limiter: FixedWindowLimiter | None = None) -> None:
    """Count one parse request for the workspace; over ``parse_rate_max`` per window is ``RATE_LIMITED``, an unreachable counter store refuses (D-19)."""
    window = limiter or FixedWindowLimiter(settings.redis)
    try:
        window.hit(f"parse:{tenant_id}", settings.ingest.parse_rate_max, settings.ingest.parse_rate_window_seconds)
    except RateLimited as limited:
        raise ServiceError(Kind.RATE_LIMITED, "rate_limited", "too many parse requests, try again shortly", retry_after=limited.retry_after) from None
    except RateLimitUnavailable:
        logger.warning("parse rate limit store unavailable tenant=%s", tenant_id)
        raise _queue_unavailable() from None


def write_rate_guard(settings: Settings, tenant_id: str, limiter: FixedWindowLimiter | None = None) -> None:
    """Count one chunk add or text edit for the workspace with the parse numbers (key ``chunk:{tenant_id}``); every one costs an embedding call."""
    window = limiter or FixedWindowLimiter(settings.redis)
    try:
        window.hit(f"chunk:{tenant_id}", settings.ingest.parse_rate_max, settings.ingest.parse_rate_window_seconds)
    except RateLimited as limited:
        raise ServiceError(Kind.RATE_LIMITED, "rate_limited", "too many chunk changes, try again shortly", retry_after=limited.retry_after) from None
    except RateLimitUnavailable:
        logger.warning("chunk rate limit store unavailable tenant=%s", tenant_id)
        raise ServiceError(Kind.UNAVAILABLE, reasons.BUSY, "chunk changes are not available, try again shortly") from None


def authorize_parse(principal: Principal, dataset_id: str) -> VisibleDataset:
    """The dataset the caller may start or cancel parsing in: ``NOT_FOUND`` when not visible, then ``FORBIDDEN`` without the permission."""
    visible = load_visible_dataset(principal, dataset_id)
    if not allowed(visible.scope.subject, AREA, MANAGE_DOCUMENT):
        raise ServiceError(Kind.FORBIDDEN, reasons.FORBIDDEN, "forbidden")
    return visible


def _load_documents(visible: VisibleDataset, principal: Principal, wanted: list[str]) -> list[Document]:
    """The requested documents in request order: one NOT_FOUND when any is outside the dataset, FORBIDDEN when the caller may not change one."""
    dataset, scope = visible.dataset, visible.scope
    with DB.connection_context():
        found = list(Document.select().where(Document.id.in_(wanted) & (Document.kb_id == dataset.id)))
    if len(found) != len(wanted):
        raise _not_found()
    by_id = {doc.id: doc for doc in found}
    ordered = [by_id[i] for i in wanted]
    for doc in ordered:
        if not can_remove_document(doc.created_by, dataset.created_by, principal.user_id, scope.subject):
            raise ServiceError(Kind.FORBIDDEN, reasons.FORBIDDEN, "forbidden")
    return ordered


def chunk_counts(settings: Settings, dataset: DatasetRecord, documents: Sequence[Document], *, doc_store: DocStoreConnection | None = None) -> dict[str, ChunkCounts]:
    """Chunk, edited and hand-added counts from the index, asked only for documents whose counter is above zero."""
    engine = doc_store if doc_store is not None else get_doc_store(settings)
    out: dict[str, ChunkCounts] = {}
    idx = index_name(dataset.tenant_id)
    try:
        for doc in documents:
            if int(doc.chunk_num or 0) <= 0:
                continue
            total = engine.stats({"doc_id": [doc.id]}, idx, dataset.id).count
            edited = engine.stats({"doc_id": [doc.id], "origin_kwd": ["edited"]}, idx, dataset.id).count
            manual = engine.stats({"doc_id": [doc.id], "origin_kwd": ["manual"]}, idx, dataset.id).count
            out[doc.id] = ChunkCounts(int(total), int(edited), int(manual))
    except DocStoreError as exc:
        logger.warning("parse could not count chunks dataset=%s error=%s", dataset.id, type(exc).__name__)
        raise _index_unavailable() from None
    return out


def _needs_confirmation(run: str, counts: ChunkCounts) -> bool:
    """The replacement rule (D-04, D-09, R-163)."""
    if run == RUN_DONE:
        return counts.chunk_count > 0
    if run == RUN_NOT_STARTED:
        return counts.manual_count > 0
    if run in (RUN_FAILED, RUN_CANCELLED):
        return counts.edited_count > 0 or counts.manual_count > 0
    return False


def _check_all(settings: Settings, visible: VisibleDataset, documents: Sequence[Document]) -> None:
    for doc in documents:
        if not parseable(doc.suffix or ""):
            raise ServiceError(Kind.INVALID, reasons.PARSE_UNAVAILABLE, "this file type cannot be parsed")
    for doc in documents:
        if not chunker_available(doc.parser_id):
            raise ServiceError(Kind.INVALID, reasons.CHUNKER_UNAVAILABLE, "this chunking method is not available yet")
    if visible.dataset.embd_id not in embedding_dimensions(visible.scope.tenant_id):
        raise ServiceError(Kind.CONFLICT, reasons.MODEL_UNAVAILABLE, "the embedding model of this dataset is no longer available")
    for doc in documents:
        if doc.run == RUN_RUNNING:
            raise ServiceError(Kind.CONFLICT, reasons.ALREADY_RUNNING, "a document is already being parsed")


def _page_ranges(settings: Settings, storage: Storage, doc: Document) -> list[tuple[int, int]]:
    """Page ranges of one document. The count comes from ``pdf_page_count`` (cached); a damaged or unreadable PDF yields the single full range (the worker fails it, D-25)."""
    total = pdf_page_count(settings, doc.id, doc.location or "", doc.content_hash or "", doc.suffix or "", storage=storage)
    selected = (doc.parser_config or {}).get("pages") if (doc.suffix or "").lower() == "pdf" else None
    if getattr(doc, "parser_id", "naive") in {"one", "paper", "laws"}:
        from rag.parsers.page_selection import selected_ranges

        bounds = (0, total if total is not None else 1_000_000)
        if not selected_ranges(selected, bounds):
            raise ServiceError(Kind.INVALID, reasons.PARSER_CONFIG_INVALID, "the selected pages are outside this document", data={"field": "pages"})
        return [bounds]
    if not selected or total is None:
        return task_service.split_pages(total, settings.ingest.task_page_size)
    ranges = sorted((max(0, start - 1), min(end, total)) for start, end in selected if start <= total)
    if not ranges:
        raise ServiceError(Kind.INVALID, reasons.PARSER_CONFIG_INVALID, "the selected pages are outside this document", data={"field": "pages"})
    merged: list[tuple[int, int]] = []
    for start, end in ranges:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return [(start, min(start + settings.ingest.task_page_size, end))
            for first, end in merged for start in range(first, end, settings.ingest.task_page_size)]


@dataclass(frozen=True)
class _Plan:
    doc: Document
    ranges: list[tuple[int, int]]


def _digest_for(doc: Document, start: int, end: int) -> str:
    cfg = dict(doc.parser_config or {})
    return task_service.task_digest(
        doc.id,
        start,
        end,
        doc.content_hash or "",
        doc.parser_id,
        int(cfg.get("chunk_token_num", _DEFAULT_CHUNK_TOKENS)),
        str(cfg.get("delimiter", _DEFAULT_DELIMITER)),
        cfg.get("overlapped_percent", 0),
        parser_config=cfg,
    )


def start_parse(
    settings: Settings,
    visible: VisibleDataset,
    principal: Principal,
    doc_ids: object,
    confirm_replace: bool,
    *,
    storage: Storage | None = None,
    doc_store: DocStoreConnection | None = None,
    queue: TaskQueue | None = None,
) -> list[ParseStarted]:
    """Start parsing the documents, all or none. See the module note for the order of the steps."""
    wanted = _clean_ids(doc_ids)
    dataset, scope = visible.dataset, visible.scope
    documents = _load_documents(visible, principal, wanted)
    _check_all(settings, visible, documents)

    counts = chunk_counts(settings, dataset, documents, doc_store=doc_store)
    if not confirm_replace:
        pending = [
            {"id": d.id, "name": d.name, "chunk_count": counts[d.id].chunk_count, "edited_count": counts[d.id].edited_count, "manual_count": counts[d.id].manual_count}
            for d in documents
            if d.id in counts and _needs_confirmation(d.run or RUN_NOT_STARTED, counts[d.id])
        ]
        if pending:
            raise ServiceError(Kind.CONFLICT, reasons.CONFIRM_REQUIRED, "starting again replaces chunks that cannot be recovered", data={"documents": pending})

    jobs = queue if queue is not None else get_queue(settings)
    try:
        jobs.ping()
    except QueueUnavailable as exc:
        logger.warning("parse found the queue unavailable dataset=%s error=%s", dataset.id, type(exc).__name__)
        raise _queue_unavailable() from None

    blobs = storage if storage is not None else get_storage(settings)
    plans = [_Plan(doc, _page_ranges(settings, blobs, doc)) for doc in documents]
    replace_ids = [d.id for d in documents if int(d.chunk_num or 0) > 0]
    engine = doc_store if doc_store is not None else get_doc_store(settings)

    with ExitStack() as locks:
        locks.enter_context(_named_lock(upload_lock_name(dataset.id), LOCK_TIMEOUT_SECONDS, "another change to this dataset is running, try again shortly"))
        _recheck_not_running(wanted)
        if replace_ids:
            try:
                engine.delete({"doc_id": replace_ids}, index_name(scope.tenant_id), dataset.id)
            except DocStoreError as exc:
                logger.warning("parse could not prune the index dataset=%s error=%s", dataset.id, type(exc).__name__)
                raise _index_unavailable() from None
        published = _write_state(visible, plans)

    try:
        for task_id, digest in published:
            jobs.enqueue(task_id, digest, 0)
    except QueueUnavailable as exc:
        logger.warning("parse could not publish dataset=%s error=%s", dataset.id, type(exc).__name__)
        fail_documents(wanted, code="queue_unavailable", step="queue")
        raise _queue_unavailable() from None
    logger.info("parse started tenant=%s dataset=%s documents=%d tasks=%d", scope.tenant_id, dataset.id, len(documents), len(published))
    return [ParseStarted(plan.doc.id, len(plan.ranges)) for plan in plans]


def _recheck_not_running(wanted: list[str]) -> None:
    with DB.connection_context():
        if Document.select(Document.id).where(Document.id.in_(wanted) & (Document.run == RUN_RUNNING)).first() is not None:
            raise ServiceError(Kind.CONFLICT, reasons.ALREADY_RUNNING, "a document is already being parsed")


def _write_state(visible: VisibleDataset, plans: Sequence[_Plan]) -> list[tuple[str, str]]:
    """One transaction (retried when MySQL picks it as a deadlock victim): lock rows in id order, replace tasks, log and reset documents."""
    dataset = visible.dataset
    ids = sorted(plan.doc.id for plan in plans)
    for attempt in range(1, DEADLOCK_ATTEMPTS + 1):
        try:
            with DB.connection_context(), transaction():
                locked = list(Document.select(Document.id, Document.kb_id, Document.run, Document.chunk_num, Document.token_num).where(Document.id.in_(ids)).order_by(Document.id).for_update())
                if len(locked) != len(ids) or any(d.kb_id != dataset.id for d in locked):
                    raise _not_found()
                if any(d.run == RUN_RUNNING for d in locked):
                    raise ServiceError(Kind.CONFLICT, reasons.ALREADY_RUNNING, "a document is already being parsed")
                old_chunks = sum(int(d.chunk_num or 0) for d in locked)
                old_tokens = sum(int(d.token_num or 0) for d in locked)
                now = current_timestamp_ms()
                stamp = {"update_time": now, "update_date": timestamp_to_date(now)}
                begin = datetime.datetime.now()
                Task.delete().where(Task.doc_id.in_(ids)).execute()
                published: list[tuple[str, str]] = []
                for plan in plans:
                    doc = plan.doc
                    for start, end in plan.ranges:
                        digest = _digest_for(doc, start, end)
                        task_id = uuid.uuid4().hex
                        Task.create(id=task_id, doc_id=doc.id, from_page=start, to_page=end, task_type=_TASK_TYPE, priority=0, digest=digest, progress=0.0, retry_count=0)
                        published.append((task_id, digest))
                    PipelineOperationLog.create(
                        id=uuid.uuid4().hex,
                        document_id=doc.id,
                        tenant_id=visible.scope.tenant_id,
                        kb_id=dataset.id,
                        parser_id=doc.parser_id,
                        document_name=(doc.name or "")[:255],
                        document_suffix=doc.suffix or "",
                        document_type=doc.type or "",
                        source_from=_SOURCE_LOCAL,
                        progress=0.0,
                        process_begin_at=begin,
                        dsl={"tasks": len(plan.ranges)},
                        task_type=_TASK_TYPE,
                        operation_status=LOG_RUNNING,
                    )
                Document.update(run=RUN_RUNNING, progress=0.0, progress_msg="", process_begin_at=begin, process_duration=0, chunk_num=0, token_num=0, **stamp).where(Document.id.in_(ids)).execute()
                if old_chunks or old_tokens:
                    Knowledgebase.update(
                        chunk_num=peewee.fn.GREATEST(Knowledgebase.chunk_num - old_chunks, 0),
                        token_num=peewee.fn.GREATEST(Knowledgebase.token_num - old_tokens, 0),
                        **stamp,
                    ).where(Knowledgebase.id == dataset.id).execute()
            return published
        except peewee.OperationalError as exc:
            if exc.args and exc.args[0] == _MYSQL_DEADLOCK and attempt < DEADLOCK_ATTEMPTS:
                logger.warning("parse transaction was a deadlock victim dataset=%s attempt=%d", dataset.id, attempt)
                continue
            raise
    raise AssertionError("unreachable: the last attempt returns or raises")


def _close_logs(doc_ids: Sequence[str], status: str, now: int) -> None:
    PipelineOperationLog.update(operation_status=status, update_time=now, update_date=timestamp_to_date(now)).where(
        PipelineOperationLog.document_id.in_(list(doc_ids)) & (PipelineOperationLog.operation_status == LOG_RUNNING)
    ).execute()


def fail_documents(doc_ids: Sequence[str], *, code: str, step: str) -> None:
    """Set the documents that are running to failed (``run`` 4, ``progress`` -1) and close their open log rows as failed."""
    ids = list(doc_ids)
    now = current_timestamp_ms()
    with DB.connection_context(), transaction():
        Document.update(run=RUN_FAILED, progress=-1.0, progress_msg=f"{step}: {code}", update_time=now, update_date=timestamp_to_date(now)).where(
            Document.id.in_(ids) & (Document.run == RUN_RUNNING)
        ).execute()
        _close_logs(ids, LOG_FAILED, now)


def cancel_parse(
    settings: Settings,
    visible: VisibleDataset,
    principal: Principal,
    doc_ids: object,
    *,
    doc_store: DocStoreConnection | None = None,
) -> list[str]:
    """Cancel the running documents among ``doc_ids`` and return their ids. Chunks and totals are kept; a document that is not running is untouched."""
    wanted = _clean_ids(doc_ids)
    dataset, scope = visible.dataset, visible.scope
    _load_documents(visible, principal, wanted)  # visibility and the per-document permission, before anything changes
    cancelled: list[str] = []
    now = current_timestamp_ms()
    with DB.connection_context(), transaction():
        locked = Document.select(Document.id, Document.run).where(Document.id.in_(sorted(wanted))).order_by(Document.id).for_update()
        cancelled = [d.id for d in locked if d.run == RUN_RUNNING]
        if cancelled:
            Document.update(run=RUN_CANCELLED, update_time=now, update_date=timestamp_to_date(now)).where(Document.id.in_(cancelled)).execute()
            _close_logs(cancelled, LOG_CANCELLED, now)
    for doc_id in cancelled:
        try:
            settle_totals(settings, scope.tenant_id, dataset.id, doc_id, doc_store=doc_store)
        except ServiceError:
            logger.warning("cancel could not settle totals dataset=%s", dataset.id)
    return cancelled
