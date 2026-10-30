"""Read, add, edit and switch the chunks of one document (plan 04-18; CHUNK-16, CHUNK-18..21, IDX-07, KB-19, BE-06, D-10, D-11, D-12, D-26, R-155).

* ``list_chunks`` pages a document's chunks in document order (parsed ones by ``order_int``, hand-added ones last by creation time). A ``keywords``
  filter goes through the shared tokenizer and the escaped ``simple_query_string`` of the document store, so punctuation in it never reaches the
  engine as syntax and never turns into an error (BE-06). The chunk's own switch is ``enabled``; the document's switch is not part of it (D-26).
* ``create_chunk`` and ``update_chunk`` embed first and write second (D-11). The embedding call is the only step that can fail slowly; when it
  fails nothing is written, so the previous text, tokens and vector stay together and no pending state exists. Text, tokens and vector of an edit
  are written in one engine operation. Every engine result is checked: ``update`` answers False when the engine reports per-document failures
  (it does not raise), which is refused as ``index_unavailable`` exactly like an engine error.
* Who may write: the uploader, the dataset's creator, the owner and an admin, judged on the permission subject so an API token is never elevated
  (``can_remove_document``). Reads need only dataset visibility. Writes are refused with 409 ``parse_running`` while the document is parsing.
* A chunk id in a path must match one of two grammars before any lookup, belong to the document and the dataset, or the answer is the one 404.

The module imports no web framework. The functions block (database, index, provider): the caller runs them in a bounded executor.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from api.apps.permissions_gen import allowed
from api.db.database import DB
from api.db.models import Document
from api.db.services.auth_service import Principal
from api.db.services.chunk_view import merge_page_sizes, page_sizes_of, positions_of
from api.db.services.document_service import AREA, MANAGE_DOCUMENT
from api.db.services.knowledgebase_service import VisibleDataset, embedding_dimensions, load_visible_dataset
from api.db.services.llm_service import LLMBundle
from api.db.services.service_errors import Kind, ServiceError
from api.db.services.tenant_scope import can_remove_document
from api.db.services.totals_service import settle_totals
from api.utils import reasons
from common.doc_store.doc_store_base import DocStoreConnection, DocStoreError, MatchTextExpr, OrderByExpr, index_name, vector_field
from common.settings import Settings
from rag.nlp.token_count import count_tokens
from rag.nlp.tokenizer import tokenize
from rag.svr.chunk_doc import ORIGIN_EDITED, ORIGIN_MANUAL, ORIGIN_PARSED, l2_normalize, manual_row, text_features
from rag.svr.failure import TaskFailure
from rag.utils.es_conn import MAX_RESULT_WINDOW, get_doc_store

logger = logging.getLogger(__name__)

CHUNK_ID_PARSED = re.compile(r"[0-9a-f]{32}_[0-9]+")
CHUNK_ID_MANUAL = re.compile(r"[0-9a-f]{32}_m_[0-9a-f]{32}")
_ID = re.compile(r"[0-9a-f]{32}")
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20
MAX_KEYWORDS = 128
MAX_CHUNK_CHARS = 32000
# The handler stops waiting after 45 s but cannot stop the worker thread. An embedding that finishes later than this is dropped instead of written,
# so an answer of "timed out" always means nothing was stored.
WRITE_DEADLINE_SECONDS = 40.0
_RUNNING = "1"
_ENABLED = "1"
from rag.chunking.tag import tag_weights
from rag.parsers.tags import TAG_FIELD, TAG_LABEL_FIELD, TagFeature
from rag.parsers.slides import slide_of
from rag.parsers.audio_segments import audio_of
from rag.parsers.table_features import TABLE_FIELD, tables_of

_LIST_FIELDS = ["content_with_weight", "position_int", "origin_kwd", "available_int", "page_dims_flt", "order_int", TABLE_FIELD, "slide_number_int", "slide_title_kwd", "audio_start_flt", "audio_end_flt"]


def _not_found() -> ServiceError:
    return ServiceError(Kind.NOT_FOUND, reasons.DATASET_NOT_FOUND, "not found")


def _index_unavailable() -> ServiceError:
    return ServiceError(Kind.UNAVAILABLE, reasons.INDEX_UNAVAILABLE, "the search index is not available, try again shortly")


def _invalid(message: str, reason: str = reasons.FIELDS_INVALID) -> ServiceError:
    return ServiceError(Kind.INVALID, reason, message)


# ----------------------------------------------------------------------------- shapes


def valid_chunk_id(chunk_id: object) -> bool:
    return isinstance(chunk_id, str) and (CHUNK_ID_PARSED.fullmatch(chunk_id) is not None or CHUNK_ID_MANUAL.fullmatch(chunk_id) is not None)


def chunk_dto(source: dict[str, Any]) -> dict[str, Any]:
    """The response body for a chunk. Keys are listed here, so a field added to the index never reaches a client unreviewed."""
    slide = slide_of(source)
    audio = audio_of(source)
    return {
        **({"audio": audio} if audio else {}),
        **({"slide": slide} if slide else {}),
        "id": str(source.get("id", "")),
        "text": str(source.get("content_with_weight") or ""),
        "positions": positions_of(source),
        "origin": str(source.get("origin_kwd") or ORIGIN_PARSED),
        "enabled": int(source.get("available_int", 1)) == 1,
        **({"tables": tables_of(source)} if source.get(TABLE_FIELD) else {}),
    }


# ----------------------------------------------------------------------------- authorisation


def authorize_read(principal: Principal, dataset_id: str) -> VisibleDataset:
    """The dataset whose chunks the caller may read: visibility only (``NOT_FOUND`` otherwise)."""
    return load_visible_dataset(principal, dataset_id)


def authorize_write(principal: Principal, dataset_id: str) -> VisibleDataset:
    """Visibility first, then ``datasets.manage_document``. Which documents the caller may change is decided per document inside each write."""
    visible = load_visible_dataset(principal, dataset_id)
    if not allowed(visible.scope.subject, AREA, MANAGE_DOCUMENT):
        raise ServiceError(Kind.FORBIDDEN, reasons.FORBIDDEN, "forbidden")
    return visible


def _document(visible: VisibleDataset, doc_id: object) -> Document:
    """The document of this dataset; the one ``NOT_FOUND`` for a malformed id or one that belongs elsewhere."""
    if not isinstance(doc_id, str) or _ID.fullmatch(doc_id) is None:
        raise _not_found()
    with DB.connection_context():
        doc = Document.select(Document.id, Document.name, Document.created_by, Document.run, Document.status, Document.parser_id, Document.parser_config).where((Document.id == doc_id) & (Document.kb_id == visible.dataset.id)).first()
    if doc is None:
        raise _not_found()
    return doc


def _writable_document(visible: VisibleDataset, principal: Principal, doc_id: object) -> Document:
    doc = _document(visible, doc_id)
    if not can_remove_document(doc.created_by, visible.dataset.created_by, principal.user_id, visible.scope.subject):
        raise ServiceError(Kind.FORBIDDEN, reasons.FORBIDDEN, "forbidden")
    _require_idle(visible, doc.id)
    return doc


def _require_idle(visible: VisibleDataset, doc_id: str) -> None:
    """A fresh read of ``run``: 409 ``parse_running`` while the document is being parsed, its chunks are being replaced."""
    with DB.connection_context():
        row = Document.select(Document.run).where((Document.id == doc_id) & (Document.kb_id == visible.dataset.id)).first()
    if row is None:
        raise _not_found()
    if row.run == _RUNNING:
        raise ServiceError(Kind.CONFLICT, reasons.PARSE_RUNNING, "this document is being parsed, wait for it to finish")


# ----------------------------------------------------------------------------- list


def _whole(value: object, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ServiceError(Kind.INVALID, reasons.QUERY_INVALID, f"{name} must be a whole number from {low} to {high}")
    return value


def list_chunks(
    settings: Settings,
    visible: VisibleDataset,
    doc_id: str,
    *,
    page: int = 1,
    size: int = DEFAULT_PAGE_SIZE,
    keywords: str | None = None,
    available: int | None = None,
    doc_store: DocStoreConnection | None = None,
) -> dict[str, Any]:
    """``{"items", "total", "page_sizes"}`` for one page of the document's chunks in document order."""
    doc = _document(visible, doc_id)
    page = _whole(page, "page", 1, MAX_RESULT_WINDOW)
    size = _whole(size, "size", 1, MAX_PAGE_SIZE)
    if available not in (None, 0, 1) or isinstance(available, bool):
        raise ServiceError(Kind.INVALID, reasons.QUERY_INVALID, "available must be 0 or 1")
    if keywords is not None and (not isinstance(keywords, str) or len(keywords) > MAX_KEYWORDS):
        raise ServiceError(Kind.INVALID, reasons.QUERY_INVALID, f"keywords must be at most {MAX_KEYWORDS} characters")
    offset = (page - 1) * size
    if offset >= MAX_RESULT_WINDOW:
        raise ServiceError(Kind.INVALID, reasons.QUERY_INVALID, "that page is beyond what can be listed")
    match: list[Any] = []
    if keywords and keywords.strip():
        tokens = tokenize(keywords)
        if not tokens:
            return {"items": [], "total": 0, "page_sizes": {}}  # punctuation only: nothing can match, and nothing is an error
        match.append(MatchTextExpr(["content_ltks"], " ".join(tokens), size, {"minimum_should_match": "100%"}))
    condition: dict[str, Any] = {"doc_id": [doc.id]}
    if available is not None:
        condition["available_int"] = [available]
    order = OrderByExpr().asc("order_int").asc("create_timestamp_flt")
    engine = doc_store if doc_store is not None else get_doc_store(settings)
    try:
        found = engine.search(
            _LIST_FIELDS, [], condition, match, order, offset, size, index_name(visible.scope.tenant_id), [visible.dataset.id]
        )
    except DocStoreError as exc:
        logger.warning("chunk list could not read the index dataset=%s error=%s", visible.dataset.id, type(exc).__name__)
        raise _index_unavailable() from None
    dtos = [chunk_dto(hit) for hit in found.hits]
    wanted = {p["page"] for dto in dtos for p in dto["positions"]}
    return {"items": dtos, "total": int(found.total), "page_sizes": merge_page_sizes(page_sizes_of(hit, wanted) for hit in found.hits)}


# ----------------------------------------------------------------------------- write helpers


def _clean_text(text: object) -> str:
    if not isinstance(text, str) or not text.strip():
        raise _invalid("the chunk text cannot be empty")
    clean = text.strip()
    if len(clean) > MAX_CHUNK_CHARS:
        raise _invalid("the chunk text is too long", reasons.CHUNK_TOO_LONG)
    return clean


def _embed(settings: Settings, visible: VisibleDataset, text: str) -> list[float]:
    """The unit-length vector of ``text`` from the dataset's embedding model. Nothing has been written when this raises."""
    dataset = visible.dataset
    dimension = embedding_dimensions(visible.scope.tenant_id).get(dataset.embd_id)
    if dimension is None:
        raise ServiceError(Kind.NOT_FOUND, reasons.MODEL_UNAVAILABLE, "that model is not available in this workspace")
    bundle = LLMBundle(visible.scope.tenant_id, dataset.embd_id, "embedding", settings=settings, expected_dimension=dimension)
    if count_tokens(text) > bundle.token_limit:
        raise _invalid("the chunk text is longer than the embedding model accepts", reasons.CHUNK_TOO_LONG)
    vectors, _ = bundle.encode([text])
    try:
        return l2_normalize(list(vectors[0]))
    except TaskFailure:
        raise ServiceError(Kind.INVALID, reasons.PROVIDER_REFUSED, "the provider returned an unusable vector") from None


def _check_deadline(started: float) -> None:
    if time.monotonic() - started > WRITE_DEADLINE_SECONDS:
        raise ServiceError(Kind.TIMEOUT, reasons.PROVIDER_TIMEOUT, "the provider did not answer in time")


def _read(engine: DocStoreConnection, visible: VisibleDataset, doc_id: str, chunk_id: str) -> dict[str, Any] | None:
    """The stored chunk of this document and dataset, or None."""
    try:
        found = engine.get(chunk_id, index_name(visible.scope.tenant_id), [visible.dataset.id])
    except DocStoreError as exc:
        logger.warning("chunk read could not reach the index dataset=%s error=%s", visible.dataset.id, type(exc).__name__)
        raise _index_unavailable() from None
    return found if found is not None and found.get("doc_id") == doc_id else None


def _settle(settings: Settings, visible: VisibleDataset, doc_id: str, engine: DocStoreConnection) -> None:
    settle_totals(settings, visible.scope.tenant_id, visible.dataset.id, doc_id, doc_store=engine)


# ----------------------------------------------------------------------------- create


def create_chunk(
    settings: Settings,
    visible: VisibleDataset,
    principal: Principal,
    doc_id: str,
    text: object,
    *,
    doc_store: DocStoreConnection | None = None,
) -> dict[str, Any]:
    """Add a hand-made chunk to the document and return it. Embeds first; a failed embedding or index write leaves the index as it was (D-11)."""
    started = time.monotonic()
    doc = _writable_document(visible, principal, doc_id)
    clean = _clean_text(text)
    vector = _embed(settings, visible, clean)
    _check_deadline(started)
    engine = doc_store if doc_store is not None else get_doc_store(settings)
    _require_idle(visible, doc.id)
    row = manual_row(
        clean,
        doc_id=doc.id,
        kb_id=visible.dataset.id,
        doc_name=doc.name,
        vector=vector,
        enabled=(doc.status or _ENABLED) == _ENABLED,
        token_num=count_tokens(clean),
        pagerank=visible.dataset.pagerank,
        meta_fields=doc.meta_fields,
        tags=tuple(TagFeature(key,value) for key,value in tag_weights(clean,(doc.parser_config or {}).get("tag_top_n",8)).items()) if doc.parser_id=="tag" else (),
    )
    index = index_name(visible.scope.tenant_id)
    try:
        engine.create_idx(index, visible.dataset.id, len(vector), visible.dataset.parser_id)
        failed = engine.insert([row], index, visible.dataset.id)
    except DocStoreError as exc:
        logger.warning("chunk add could not write the index dataset=%s error=%s", visible.dataset.id, type(exc).__name__)
        raise _index_unavailable() from None
    if failed:
        raise _index_unavailable()
    _settle(settings, visible, doc.id, engine)
    logger.info("chunk added tenant=%s dataset=%s document=%s", visible.scope.tenant_id, visible.dataset.id, doc.id)
    return chunk_dto(row)


# ----------------------------------------------------------------------------- update


def update_chunk(
    settings: Settings,
    visible: VisibleDataset,
    principal: Principal,
    doc_id: str,
    chunk_id: str,
    *,
    text: object = None,
    available: object = None,
    doc_store: DocStoreConnection | None = None,
) -> dict[str, Any]:
    """Change a chunk's text and/or its own search switch and return it. With text: embed first, then write text, tokens and vector in one operation."""
    started = time.monotonic()
    if not valid_chunk_id(chunk_id):
        raise _not_found()
    if text is None and available is None:
        raise _invalid("send text or available")
    if available is not None and not isinstance(available, bool):
        raise _invalid("available must be true or false")
    doc = _writable_document(visible, principal, doc_id)
    clean = None if text is None else _clean_text(text)
    engine = doc_store if doc_store is not None else get_doc_store(settings)
    stored = _read(engine, visible, doc.id, chunk_id)
    if stored is None:
        raise _not_found()

    values: dict[str, Any] = {}
    if clean is not None:
        if stored.get(TABLE_FIELD):
            values[TABLE_FIELD] = ""
        vector = _embed(settings, visible, clean)  # any failure ends here: nothing has been written
        _check_deadline(started)
        features = text_features(clean)
        if doc.parser_id == "tag" or stored.get(TAG_FIELD):
            weights = tag_weights(clean,(doc.parser_config or {}).get("tag_top_n",8)) if doc.parser_id == "tag" else {}
            features.update({TAG_FIELD:weights,TAG_LABEL_FIELD:list(weights)})
        if stored.get("content_token_offsets_int") and "content_token_offsets_int" not in features:
            features["content_token_offsets_int"] = []
        values.update(
            {
                "content_with_weight": clean,
                **features,
                "token_num_int": count_tokens(clean),
                vector_field(len(vector)): vector,
                "origin_kwd": ORIGIN_MANUAL if stored.get("origin_kwd") == ORIGIN_MANUAL else ORIGIN_EDITED,
            }
        )
    if available is not None:
        values["available_int"] = 1 if available else 0
    _require_idle(visible, doc.id)
    try:
        # update_by_query runs with conflicts="proceed": per-document failures come back as False, not as an exception.
        done = engine.update({"id": [chunk_id], "doc_id": [doc.id]}, values, index_name(visible.scope.tenant_id), visible.dataset.id)
    except DocStoreError as exc:
        logger.warning("chunk edit could not write the index dataset=%s error=%s", visible.dataset.id, type(exc).__name__)
        raise _index_unavailable() from None
    if not done:
        raise _index_unavailable()
    fresh = _read(engine, visible, doc.id, chunk_id)
    if fresh is None:
        raise _not_found()  # the chunk went away meanwhile (a re-parse replaced it)
    if clean is not None:
        _settle(settings, visible, doc.id, engine)
    logger.info("chunk changed tenant=%s dataset=%s document=%s text=%s switch=%s", visible.scope.tenant_id, visible.dataset.id, doc.id, clean is not None, available is not None)
    return chunk_dto(fresh)
