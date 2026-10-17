"""The read side of ingestion: summary counts, the parsing log, one log entry, task status and the embedding-model check (plan 04-19).

KB-14, KB-15, KB-16, KB-19, DOC-22, DOC-23, D-07, D-08, D-23.

* ``ingestion_summary`` is one grouped statement over the dataset's documents. ``partial`` counts failed or cancelled documents that still hold
  chunks (they are also counted under ``failed`` or ``cancelled``); the totals are the dataset's maintained counters, never a recount.
* ``list_logs`` and ``get_log`` read ``pipeline_operation_log``. The outcome key is ``result`` (never ``status``). Every DTO is built from an explicit
  key list. An error is ``{step, code, message}`` where the sentence comes from the code (``PLAIN_MESSAGES``); stored free text is never copied.
  The only free text is ``detail`` of a ``provider_refused`` failure, scrubbed and cut to 300 characters.
* ``task_status`` resolves task, document and dataset from MySQL and applies the same visibility rule as any dataset route.
* ``embedding_check`` spends one provider call on a fixed probe string and compares the vector length with the dimension the dataset was built for.

The module imports no web framework. The functions block (database, provider): the caller runs them in a bounded executor.
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Mapping
from typing import Any

import peewee

from api.db.database import DB
from api.db.models import Document, PipelineOperationLog, Task
from api.db.services.auth_service import Principal
from api.db.services.knowledgebase_service import VisibleDataset, _require_manage, embedding_dimensions, load_visible_dataset
from api.db.services.llm_service import LLMBundle
from api.db.services.service_errors import Kind, ServiceError
from api.db.services.task_service import MAX_PROGRESS_LINES
from api.utils import reasons
from common.ingest_codes import FAILURE_CODES, LOG_CANCELLED, LOG_DONE, LOG_FAILED, LOG_RUNNING, PLAIN_MESSAGES, STEPS
from common.log_utils import redact_text
from common.settings import Settings, get_settings
from rag.svr.failure import MAX_DETAIL, UNEXPECTED, parse_failure_line

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
MAX_PAGE = 1_000_000_000
MAX_LOG_LINES = MAX_PROGRESS_LINES  # 3000
MAX_LINE_CHARS = 400
PROBE_TEXT = "devRag embedding check"  # fixed: nothing a client sends reaches the provider
_ID = re.compile(r"[0-9a-f]{32}")
_RESULTS = (LOG_RUNNING, LOG_DONE, LOG_FAILED, LOG_CANCELLED)
_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://\S+")
_PATH = re.compile(r"(?<![\w:/])/(?:[\w.\-~@%+=,]+/)+[\w.\-~@%+=,]*|(?<![\w:/])[A-Za-z]:\\\S+")
_TRACE = re.compile(r"Traceback|File \"")

LOG_KEYS: tuple[str, ...] = (
    "id", "document_id", "document_name", "started_at", "duration_seconds", "result", "attempts", "max_attempts", "retried", "chunk_count",
    "pages_total", "pages_without_text", "error",
)  # fmt: skip
TASK_KEYS: tuple[str, ...] = (
    "id", "doc_id", "dataset_id", "from_page", "to_page", "progress", "progress_message", "attempts", "finished", "failed", "error",
)  # fmt: skip
SUMMARY_KEYS: tuple[str, ...] = ("unstart", "running", "done", "failed", "cancelled", "partial", "chunk_total", "token_total")


def _not_found() -> ServiceError:
    return ServiceError(Kind.NOT_FOUND, reasons.DATASET_NOT_FOUND, "not found")


def _query_invalid(message: str) -> ServiceError:
    return ServiceError(Kind.INVALID, reasons.QUERY_INVALID, message)


def _whole(value: object, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise _query_invalid(f"{name} must be a whole number from {low} to {high}")
    return value


# ----------------------------------------------------------------------------- scrubbing


def scrub_text(text: str) -> str:
    """Keys, user:password pairs, URLs and absolute paths replaced; nothing of the original location or host survives."""
    clean = redact_text(" ".join(str(text).split()))
    return _PATH.sub("[path]", _URL.sub("[url]", clean))


def _line(text: object) -> str | None:
    """One progress line for a client, or None for a line that is a stack trace."""
    raw = str(text or "").strip()
    if not raw or _TRACE.search(raw):
        return None
    return scrub_text(raw)[:MAX_LINE_CHARS] or None


def _lines(text: object) -> list[str]:
    tail = str(text or "").splitlines()[-MAX_LOG_LINES:]
    return [line for line in map(_line, tail) if line]


def _last_line(text: object) -> str:
    for raw in reversed(str(text or "").splitlines()):
        line = _line(raw)
        if line:
            return line
    return ""


# ----------------------------------------------------------------------------- errors


def _error(step: object, code: object, detail: object = None) -> dict[str, str]:
    """The error object: step and code are checked against the vocabulary, the sentence comes from the code, ``detail`` only for a refusal."""
    known = code if code in FAILURE_CODES else UNEXPECTED
    out = {"step": step if step in STEPS else "parse", "code": known, "message": PLAIN_MESSAGES[known]}
    if known == reasons.PROVIDER_REFUSED and isinstance(detail, str):
        text = scrub_text(detail)[:MAX_DETAIL]
        if text:
            out["detail"] = text
    return out


def _error_of_dsl(dsl: Mapping[str, Any]) -> dict[str, str]:
    raw = dsl.get("error")
    raw = raw if isinstance(raw, dict) else {}
    return _error(raw.get("step"), raw.get("code"), raw.get("detail"))


# ----------------------------------------------------------------------------- authorisation


def authorize_read(principal: Principal, dataset_id: str) -> VisibleDataset:
    """Visibility only: ``NOT_FOUND`` for an absent, foreign or invisible dataset."""
    return load_visible_dataset(principal, dataset_id)


def authorize_check(principal: Principal, dataset_id: str) -> VisibleDataset:
    """Visibility, then the dataset manage rule (creator, owner or admin). Runs before the limiter so a refused caller costs no window slot."""
    visible = load_visible_dataset(principal, dataset_id)
    _require_manage(visible, principal.user_id)
    return visible


# ----------------------------------------------------------------------------- summary


def ingestion_summary(visible: VisibleDataset) -> dict[str, int]:
    """Document counts by state from one grouped statement; the chunk and token totals are the dataset's own counters."""
    counts = {"unstart": 0, "running": 0, "done": 0, "failed": 0, "cancelled": 0}
    names = {"0": "unstart", "1": "running", "2": "cancelled", "3": "done", "4": "failed"}
    partial = 0
    with_chunks = peewee.fn.COALESCE(peewee.fn.SUM(peewee.Case(None, [(Document.chunk_num > 0, 1)], 0)), 0)
    query = Document.select(Document.run, peewee.fn.COUNT(Document.id).alias("n"), with_chunks.alias("kept")).where(Document.kb_id == visible.dataset.id).group_by(Document.run)
    with DB.connection_context():
        rows = [(r.run, int(r.n), int(r.kept)) for r in query]
    for run, count, kept in rows:
        name = names.get(run or "0", "unstart")
        counts[name] += count
        if name in ("failed", "cancelled"):
            partial += kept
    return {**counts, "partial": partial, "chunk_total": int(visible.dataset.chunk_num), "token_total": int(visible.dataset.token_num)}


# ----------------------------------------------------------------------------- log


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _duration(log: PipelineOperationLog) -> float:
    if log.operation_status == LOG_RUNNING and log.process_begin_at is not None:
        return round(max((datetime.datetime.now() - log.process_begin_at).total_seconds(), 0.0), 1)
    return round(float(log.process_duration or 0.0), 1)


def log_dto(log: PipelineOperationLog, max_attempts: int, live_chunks: object) -> dict[str, Any]:
    """One parsing run. Keys are listed in ``LOG_KEYS``; a column added to the table never reaches a client unreviewed."""
    dsl = log.dsl if isinstance(log.dsl, dict) else {}
    result = log.operation_status if log.operation_status in _RESULTS else LOG_FAILED
    stored = _count(dsl.get("chunks"))
    if result == LOG_RUNNING:
        chunks = _count(live_chunks)
    elif result == LOG_CANCELLED and not stored:
        chunks = _count(live_chunks)  # a cancelled run keeps what it indexed before the stop; the roll-up may not have counted it yet
    else:
        chunks = stored
    return {
        "id": log.id,
        "document_id": log.document_id,
        "document_name": log.document_name,
        "started_at": int(log.create_time or 0),
        "duration_seconds": _duration(log),
        "result": result,
        "attempts": _count(dsl.get("attempts")) or 0,
        "max_attempts": max_attempts,
        "retried": dsl.get("retried") is True,
        "chunk_count": chunks or 0,
        "pages_total": _count(dsl.get("pages_total")),
        "pages_without_text": _count(dsl.get("pages_without_text")),
        "error": _error_of_dsl(dsl) if result == LOG_FAILED else None,
    }


def _log_columns() -> tuple[Any, ...]:
    return (
        PipelineOperationLog.id, PipelineOperationLog.document_id, PipelineOperationLog.document_name, PipelineOperationLog.create_time,
        PipelineOperationLog.process_begin_at, PipelineOperationLog.process_duration, PipelineOperationLog.operation_status, PipelineOperationLog.dsl,
    )  # fmt: skip


def list_logs(visible: VisibleDataset, page: object = 1, size: object = DEFAULT_PAGE_SIZE, *, settings: Settings | None = None) -> dict[str, Any]:
    """The dataset's parsing runs, newest first: ``{"items", "total"}``."""
    page = _whole(page, "page", 1, MAX_PAGE)
    size = _whole(size, "size", 1, MAX_PAGE_SIZE)
    where = PipelineOperationLog.kb_id == visible.dataset.id
    query = (
        PipelineOperationLog.select(*_log_columns(), Document.chunk_num.alias("live_chunks"))
        .join(Document, peewee.JOIN.LEFT_OUTER, on=(PipelineOperationLog.document_id == Document.id))
        .where(where)
        .order_by(PipelineOperationLog.create_time.desc(), PipelineOperationLog.id)
        .paginate(page, size)
        .objects()
    )
    with DB.connection_context():
        rows = list(query)
        total = PipelineOperationLog.select().where(where).count()
    attempts = (settings or get_settings()).ingest.max_attempts
    return {"items": [log_dto(r, attempts, getattr(r, "live_chunks", None)) for r in rows], "total": total}


def get_log(visible: VisibleDataset, log_id: object, *, settings: Settings | None = None) -> dict[str, Any]:
    """One run with its progress lines (at most 3000, redacted). A run of another dataset is the one ``NOT_FOUND``."""
    if not isinstance(log_id, str) or _ID.fullmatch(log_id) is None:
        raise _not_found()
    query = (
        PipelineOperationLog.select(*_log_columns(), PipelineOperationLog.progress_msg, Document.chunk_num.alias("live_chunks"))
        .join(Document, peewee.JOIN.LEFT_OUTER, on=(PipelineOperationLog.document_id == Document.id))
        .where((PipelineOperationLog.id == log_id) & (PipelineOperationLog.kb_id == visible.dataset.id))
        .objects()
    )
    with DB.connection_context():
        row = query.first()
    if row is None:
        raise _not_found()
    return {**log_dto(row, (settings or get_settings()).ingest.max_attempts, getattr(row, "live_chunks", None)), "log": _lines(row.progress_msg)}


# ----------------------------------------------------------------------------- task status


def task_status(principal: Principal, task_id: object) -> dict[str, Any]:
    """A task by id. Task, document and dataset come from MySQL; the dataset must be visible to the caller, otherwise the one ``NOT_FOUND``."""
    if not isinstance(task_id, str) or _ID.fullmatch(task_id) is None:
        raise _not_found()
    query = (
        Task.select(Task.id, Task.doc_id, Task.from_page, Task.to_page, Task.progress, Task.progress_msg, Task.retry_count, Document.kb_id)
        .join(Document, on=(Task.doc_id == Document.id))
        .where(Task.id == task_id)
    )
    with DB.connection_context():
        row = query.first()
    if row is None:
        raise _not_found()
    dataset_id = row.document.kb_id
    load_visible_dataset(principal, dataset_id)
    progress = float(row.progress or 0.0)
    found = parse_failure_line(row.progress_msg) if progress < 0 else None
    return {
        "id": row.id,
        "doc_id": row.doc_id,
        "dataset_id": dataset_id,
        "from_page": int(row.from_page or 0),
        "to_page": int(row.to_page or 0),
        "progress": progress,
        "progress_message": _last_line(row.progress_msg),
        "attempts": int(row.retry_count or 0),
        "finished": progress >= 1.0,
        "failed": progress < 0,
        "error": (_error(found.step, found.code, found.detail) if found else _error("parse", UNEXPECTED)) if progress < 0 else None,
    }


# ----------------------------------------------------------------------------- embedding check


def _model_unavailable() -> ServiceError:
    """A typed 409: the one 404 hides reasons, and here the caller already sees the dataset, so the reason is safe to show."""
    return ServiceError(Kind.CONFLICT, reasons.MODEL_UNAVAILABLE, "that model is not available in this workspace")


def embedding_check(settings: Settings, visible: VisibleDataset, principal: Principal, embd_id: str | None = None) -> dict[str, Any]:
    """Embed the probe string once and compare the vector length with the dimension the dataset's index was built for.

    ``embd_id`` names another embedding model of the workspace to try; without it the dataset's own model is used. A size difference is an answer
    (``ok`` false), not an error. A provider failure raises its typed reason; a model that is not in the workspace is ``model_unavailable``.
    """
    _require_manage(visible, principal.user_id)
    tenant_id = visible.scope.tenant_id
    expected = embedding_dimensions(tenant_id).get(visible.dataset.embd_id)
    if expected is None:
        raise _model_unavailable()
    model = visible.dataset.embd_id if embd_id is None else embd_id
    if not isinstance(model, str):
        raise _model_unavailable()
    try:
        bundle = LLMBundle(tenant_id, model, "embedding", settings=settings)  # unknown or non-embedding model: refused before any call
    except ServiceError as exc:
        if exc.kind is Kind.NOT_FOUND:
            raise _model_unavailable() from None
        raise
    vectors, _ = bundle.encode([PROBE_TEXT])
    dimension = len(vectors[0]) if vectors else 0
    return {"ok": dimension == expected, "dimension": dimension, "expected": expected}
