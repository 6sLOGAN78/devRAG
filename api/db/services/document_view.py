"""Document list rows and detail for the SPA (plan 04-15; DOC-12, DOC-20, DOC-23, D-07).

The API supplies facts and never invents a state: a document that failed or was cancelled while chunks remain is "Partly indexed" in the SPA
from ``run`` and ``chunk_count``. ``ROW_KEYS`` is the whole list of keys, so a column added to the table never reaches a client unreviewed.
The document ``status`` column (the search switch) surfaces as ``enabled``.

A page costs at most four statements: the documents, their total, one batched read of the newest log row of each document, and the progress
messages of the rows that are running or failed (the last 2,000 characters only). No call goes to the document store.
This module imports no web framework.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import peewee

from api.db.database import DB
from api.db.models import Document, PipelineOperationLog
from api.db.services.document_service import MAX_KEYWORDS, MAX_PAGE_SIZE, _escape_like, _query_invalid
from api.db.services.knowledgebase_service import DEFAULT_PARSER_CONFIG, VisibleDataset
from api.db.services.pdf_pages import pdf_page_count
from api.db.services.service_errors import Kind, ServiceError
from api.utils import reasons
from common.ingest_codes import FAILURE_CODES, PLAIN_MESSAGES, RUN_FAILED, RUN_RUNNING, STEPS
from common.log_utils import redact_text
from common.settings import Settings
from rag.parsers.router import parseable
from rag.utils.storage_base import Storage

ROW_KEYS: tuple[str, ...] = (
    "id", "name", "size", "type", "suffix", "dataset_id", "created_by", "parser_id", "create_time", "update_time",
    "run", "progress", "progress_message", "chunk_count", "token_num", "parseable", "enabled", "thumbnail", "last_log_id",
    "pages_total", "pages_without_text", "error",
)  # fmt: skip
MAX_MESSAGE = 300
MESSAGE_TAIL = 2000
MAX_THUMBNAIL = 20000
THUMBNAIL_PREFIXES = ("data:image/jpeg;base64,", "data:image/png;base64,")
_ENABLED = "1"


def _columns() -> tuple[Any, ...]:
    thumb = peewee.Case(None, [(peewee.fn.LENGTH(Document.thumbnail) <= MAX_THUMBNAIL, Document.thumbnail)], None).alias("thumb")  # large values never leave the database
    return (
        Document.id, Document.name, Document.size, Document.type, Document.suffix, Document.run, Document.progress, Document.kb_id,
        Document.created_by, Document.parser_id, Document.chunk_num, Document.token_num, Document.create_time, Document.update_time,
        Document.status, thumb,
    )  # fmt: skip


def _thumbnail(value: object) -> str | None:
    if isinstance(value, str) and len(value) <= MAX_THUMBNAIL and value.startswith(THUMBNAIL_PREFIXES):
        return value
    return None


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _error_of(latest: Mapping[str, Any] | None) -> dict[str, str]:
    raw = (latest or {}).get("dsl")
    raw = raw.get("error") if isinstance(raw, dict) else None
    raw = raw if isinstance(raw, dict) else {}
    code = raw.get("code") if raw.get("code") in FAILURE_CODES else "unexpected"
    step = raw.get("step") if raw.get("step") in STEPS else "parse"
    return {"step": step, "code": code, "message": PLAIN_MESSAGES[code]}  # the sentence comes from the typed code, never from stored text


def _last_line(text: object) -> str:
    if not isinstance(text, str):
        return ""
    for line in reversed(text.splitlines()):
        if line.strip():
            return redact_text(line.strip())[:MAX_MESSAGE]
    return ""


def row_dto(doc: Document, latest_log: Mapping[str, Any] | None, progress_message: str) -> dict[str, Any]:
    """One document as the list and detail show it. ``latest_log`` is ``{"id", "dsl"}`` of the newest log row, or ``None``."""
    dsl = (latest_log or {}).get("dsl")
    dsl = dsl if isinstance(dsl, dict) else {}
    return {
        "id": doc.id,
        "name": doc.name,
        "size": int(doc.size or 0),
        "type": doc.type,
        "suffix": doc.suffix,
        "dataset_id": doc.kb_id,
        "created_by": doc.created_by,
        "parser_id": doc.parser_id,
        "create_time": int(doc.create_time or 0),
        "update_time": int(doc.update_time or 0),
        "run": doc.run,
        "progress": float(doc.progress or 0.0),
        "progress_message": progress_message,
        "chunk_count": int(doc.chunk_num or 0),
        "token_num": int(doc.token_num or 0),
        "parseable": parseable(doc.suffix or ""),
        "enabled": doc.status == _ENABLED,
        "thumbnail": _thumbnail(getattr(doc, "thumb", None)),
        "last_log_id": latest_log["id"] if latest_log else None,
        "pages_total": _count(dsl.get("pages_total")),
        "pages_without_text": _count(dsl.get("pages_without_text")),
        "error": _error_of(latest_log) if doc.run == RUN_FAILED else None,
    }


def _latest_logs(ids: list[str]) -> dict[str, dict[str, Any]]:
    """The newest log row of each document, from one select (the message column is not read)."""
    latest: dict[str, dict[str, Any]] = {}
    if not ids:
        return latest
    query = (
        PipelineOperationLog.select(PipelineOperationLog.id, PipelineOperationLog.document_id, PipelineOperationLog.dsl)
        .where(PipelineOperationLog.document_id.in_(ids))
        .order_by(PipelineOperationLog.create_time.desc(), PipelineOperationLog.id)
    )
    for log in query:
        latest.setdefault(log.document_id, {"id": log.id, "dsl": log.dsl})
    return latest


def _messages(ids: list[str]) -> dict[str, str]:
    """The last line of the progress message of the given (running or failed) documents; only the tail of the column is read."""
    if not ids:
        return {}
    tail = peewee.fn.RIGHT(Document.progress_msg, MESSAGE_TAIL).alias("tail")
    return {row.id: _last_line(row.tail) for row in Document.select(Document.id, tail).where(Document.id.in_(ids))}


def _rows(docs: list[Document]) -> list[dict[str, Any]]:
    ids = [doc.id for doc in docs]
    logs = _latest_logs(ids)
    messages = _messages([doc.id for doc in docs if doc.run in (RUN_RUNNING, RUN_FAILED)])
    return [row_dto(doc, logs.get(doc.id), messages.get(doc.id, "")) for doc in docs]


def list_rows(visible: VisibleDataset, *, page: int, page_size: int, keywords: str | None) -> tuple[list[dict[str, Any]], int]:
    """One page of the dataset's documents, newest first, with the Phase 4 facts, and the number of matches."""
    if keywords is not None and (not isinstance(keywords, str) or len(keywords) > MAX_KEYWORDS):
        raise _query_invalid(f"keywords must be at most {MAX_KEYWORDS} characters")
    page = max(1, int(page))
    page_size = min(max(1, int(page_size)), MAX_PAGE_SIZE)
    where = Document.kb_id == visible.dataset.id
    if keywords:
        pattern = f"%{_escape_like(keywords)}%"
        where = where & peewee.NodeList((Document.name, peewee.SQL("LIKE"), pattern, peewee.SQL("ESCAPE '\\\\'")))
    with DB.connection_context():
        total = Document.select().where(where).count()
        docs = list(Document.select(*_columns()).where(where).order_by(Document.create_time.desc(), Document.id).paginate(page, page_size))
        return _rows(docs), total


def document_detail(settings: Settings, visible: VisibleDataset, doc_id: str, *, storage: Storage | None = None) -> dict[str, Any]:
    """One document of a visible dataset: the row facts plus its chunking settings and whether pages can be previewed."""
    with DB.connection_context():
        doc = Document.select(*_columns(), Document.parser_config, Document.content_hash, Document.location).where((Document.id == doc_id) & (Document.kb_id == visible.dataset.id)).first()
        if doc is None:
            raise ServiceError(Kind.NOT_FOUND, reasons.DATASET_NOT_FOUND, "not found")
        body = _rows([doc])[0]
    config = {**DEFAULT_PARSER_CONFIG, **(doc.parser_config if isinstance(doc.parser_config, dict) else {})}
    if body["pages_total"] is None and (doc.suffix or "").lower() == "pdf":
        body["pages_total"] = pdf_page_count(settings, doc.id, doc.location or "", doc.content_hash or "", doc.suffix or "", storage=storage)
    body.update(
        chunk_token_num=config["chunk_token_num"],
        delimiter=config["delimiter"],
        overlapped_percent=int(config.get("overlapped_percent") or 0),
        preview="pages" if (doc.suffix or "").lower() == "pdf" and body["pages_total"] is not None else "none",
    )
    return body
