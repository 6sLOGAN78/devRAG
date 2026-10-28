"""Retrieval test: authorise datasets, embed the question once, search, prune and shape the answer (plan 05-04; RETR-16..18, RETR-23, KB-18, TEN-03, D-19, D-20, R-22).

``search`` is the Python implementation of the retrieval driver behind ``POST /api/v1/datasets/search``. One call acts in one workspace (RETR-16 is
Partial: several datasets of that workspace, never several workspaces). Every dataset id is opened with ``load_visible_dataset`` and must belong to the acting
workspace; any id the caller cannot open, that belongs elsewhere or that does not exist is the one NOT_FOUND for the whole request and no search runs.
All datasets of a call share one embedding model, because the question is embedded once (``embedding_mismatch``).

An optional ``rerank_id`` adds a rerank stage (plan 05-05, D-03, R-197): the first ``rerank_max_candidates`` candidates are scored by the workspace's rerank
model and a failure of that stage is a 502 ``rerank_unavailable``; there is never a silent fall back to the fusion order.

The question text is never logged and never copied into an error. Logs carry dataset ids and exception class names only. The function blocks (database,
provider, index): the caller runs it, and the rate guard, in a bounded executor.
"""

from __future__ import annotations

import logging
import math
import re
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from api.db.database import DB
from api.db.models import Document
from api.db.services.auth_service import Principal
from api.db.services.chunk_view import chunk_view_fields
from api.db.services.dialog_records import AssistantRecord
from api.db.services.knowledgebase_service import VisibleDataset, embedding_dimensions, load_visible_dataset
from api.db.services.llm_service import LLMBundle
from api.db.services.service_errors import Kind, ServiceError
from api.db.services.tenant_scope import ActingScope
from api.utils import reasons
from common.doc_store.doc_store_base import DocStoreConnection, DocStoreError
from common.ratelimit import FixedWindowLimiter, RateLimited, RateLimitUnavailable
from common.settings import Settings
from rag.nlp.fusion import sanitize_floats
from rag.nlp.search import FUSIONS, Hit, RetrievalRequest, RetrievalResult, Retriever
from rag.nlp.synonym import SynonymSource
from rag.svr.chunk_doc import l2_normalize
from rag.svr.failure import TaskFailure
from rag.utils.es_conn import get_doc_store

logger = logging.getLogger(__name__)

_ID = re.compile(r"[0-9a-f]{32}")
MAX_QUESTION_CHARS = 2000
MAX_DATASETS = 10
MAX_DOC_IDS = 100
MIN_TOP_K = 16
MAX_PAGE_SIZE = 100
MAX_MODEL_ID_CHARS = 128
DEFAULT_PAGE_SIZE = 10

Embedder = Callable[[str], list[float]]
Reranker = Callable[[str, list[str]], list[float]]


def _invalid(message: str, reason: str = reasons.FIELDS_INVALID) -> ServiceError:
    return ServiceError(Kind.INVALID, reason, message)


def _not_found() -> ServiceError:
    return ServiceError(Kind.NOT_FOUND, reasons.DATASET_NOT_FOUND, "not found")


# ----------------------------------------------------------------------------- rate limit


def retrieval_rate_guard(settings: Settings, tenant_id: str, user_id: str, limiter: FixedWindowLimiter | None = None) -> None:
    """Count one retrieval test for the workspace and user (key ``retrieval:{tenant}:{user}``); every call costs an embedding. An unreachable store refuses."""
    window = limiter or FixedWindowLimiter(settings.redis)
    try:
        window.hit(f"retrieval:{tenant_id}:{user_id}", settings.retrieval.rate_max, settings.retrieval.rate_window_seconds)
    except RateLimited as limited:
        raise ServiceError(Kind.RATE_LIMITED, "rate_limited", "too many retrieval tests, try again shortly", retry_after=limited.retry_after) from None
    except RateLimitUnavailable:
        logger.warning("retrieval rate limit store unavailable tenant=%s", tenant_id)
        raise ServiceError(Kind.UNAVAILABLE, reasons.BUSY, "retrieval is not available, try again shortly") from None


# ----------------------------------------------------------------------------- the body


def _whole(value: object, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise _invalid(f"{name} must be a whole number from {low} to {high}")
    return value


def _unit(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise _invalid(f"{name} must be a number from 0 to 1")
    return float(value)


def _ids(value: object, name: str, low: int, high: int, reason: str) -> list[str]:
    if not isinstance(value, list) or not low <= len(value) <= high:
        raise _invalid(f"{name} must hold {low} to {high} ids", reason)
    if any(not isinstance(v, str) or _ID.fullmatch(v) is None for v in value) or len(set(value)) != len(value):
        raise _invalid(f"{name} must be distinct ids", reason)
    return list(value)


def _question(value: object) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not text or len(text) > MAX_QUESTION_CHARS:
        raise _invalid(f"the question must be 1 to {MAX_QUESTION_CHARS} characters", reasons.QUESTION_INVALID)
    return text


def _model_unavailable() -> ServiceError:
    return ServiceError(Kind.CONFLICT, reasons.MODEL_UNAVAILABLE, "that model is not available in this workspace")


def _rerank_id(value: object) -> str | None:
    """``None`` for no rerank; otherwise a non-empty composite model id. One that is too long cannot name any model: ``model_unavailable``."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise _invalid("rerank_id must be a model id")
    if len(value) > MAX_MODEL_ID_CHARS:
        raise _model_unavailable()
    return value


def parse_body(body: Mapping[str, Any], settings: Settings) -> dict[str, Any]:
    """The checked request values. Nothing from the body is echoed into a message."""
    top_k = body.get("top_k")
    ceiling = settings.retrieval.top_k
    doc_ids = body.get("doc_ids")
    fusion = body.get("fusion", "weighted_sum")
    if fusion not in FUSIONS:
        raise _invalid("fusion must be weighted_sum or rrf")
    return {
        "question": _question(body.get("question")),
        "dataset_ids": _ids(body.get("dataset_ids"), "dataset_ids", 1, MAX_DATASETS, reasons.FIELDS_INVALID),
        "doc_ids": None if doc_ids is None else _ids(doc_ids, "doc_ids", 0, MAX_DOC_IDS, reasons.IDS_INVALID),
        "similarity_threshold": _unit(body.get("similarity_threshold", 0.2), "similarity_threshold"),
        "vector_similarity_weight": _unit(body.get("vector_similarity_weight", 0.3), "vector_similarity_weight"),
        "rerank_id": _rerank_id(body.get("rerank_id")),
        "top_k": ceiling if top_k is None else _whole(top_k, "top_k", min(MIN_TOP_K, ceiling), ceiling),
        "fusion": fusion,
        "page": _whole(body.get("page", 1), "page", 1, 10**6),
        "size": _whole(body.get("size", DEFAULT_PAGE_SIZE), "size", 1, MAX_PAGE_SIZE),
    }


# ----------------------------------------------------------------------------- authorisation and embedding


def _authorize(principal: Principal, scope: ActingScope, dataset_ids: list[str]) -> list[VisibleDataset]:
    """Every dataset opened for the caller in the acting workspace, or the one NOT_FOUND for the whole request."""
    opened = [load_visible_dataset(principal, dataset_id) for dataset_id in dataset_ids]
    if any(v.scope.tenant_id != scope.tenant_id for v in opened):
        raise _not_found()
    return opened


def _one_model(opened: list[VisibleDataset]) -> str:
    models = {v.dataset.embd_id for v in opened}
    if len(models) != 1:
        raise _invalid("the datasets use different embedding models, search them one model at a time", reasons.EMBEDDING_MISMATCH)
    return models.pop()


def _embed_question(settings: Settings, tenant_id: str, model_id: str, question: str, embedder: Embedder | None) -> list[float]:
    """The unit-length query vector. A model error keeps the bundle's own typed ``ServiceError``."""
    if embedder is not None:
        raw = embedder(question)
    else:
        dimension = embedding_dimensions(tenant_id).get(model_id)
        if dimension is None:
            raise ServiceError(Kind.NOT_FOUND, reasons.MODEL_UNAVAILABLE, "that model is not available in this workspace")
        raw, _ = LLMBundle(tenant_id, model_id, "embedding", settings=settings, expected_dimension=dimension).encode_queries(question)
    try:
        return l2_normalize(list(raw))
    except TaskFailure:
        raise ServiceError(Kind.INVALID, reasons.PROVIDER_REFUSED, "the provider returned an unusable vector") from None


def _build_reranker(settings: Settings, tenant_id: str, rerank_id: str | None, reranker: Reranker | None) -> Reranker | None:
    """The reranker seam for the Retriever, or ``None`` without a rerank model.

    The bundle is built from the acting workspace's own credential rows, so another workspace's model is the same ``model_unavailable`` as an unknown id.
    Any failure of the rerank call itself (provider error, timeout, an answer of the wrong size) becomes one 502 ``rerank_unavailable`` and no partial result.
    """
    if rerank_id is None:
        return None
    if reranker is None:
        try:
            bundle = LLMBundle(tenant_id, rerank_id, "rerank", settings=settings)
        except ServiceError as refused:
            if refused.reason == reasons.MODEL_UNAVAILABLE:
                raise _model_unavailable() from None
            raise
        reranker = bundle.rerank

    def guarded(query: str, texts: list[str]) -> list[float]:
        try:
            scores = reranker(query, texts)
            if len(scores) != len(texts):
                raise ValueError("score count")
            return scores
        except Exception as exc:  # noqa: BLE001 - fail closed: every failure of this stage is the one typed answer
            logger.warning("rerank stage failed tenant=%s error=%s", tenant_id, type(exc).__name__)
        raise ServiceError(Kind.BAD_GATEWAY, reasons.RERANK_UNAVAILABLE, "the rerank model could not be used, try again shortly")

    return guarded


def _documents_that_exist(dataset_ids: list[str]) -> Callable[[set[str]], Iterable[str]]:
    def alive(doc_ids: set[str]) -> list[str]:
        if not doc_ids:
            return []
        with DB.connection_context():
            rows = Document.select(Document.id).where(Document.id.in_(sorted(doc_ids)) & Document.kb_id.in_(dataset_ids))
            return [row.id for row in rows]

    return alive


# ----------------------------------------------------------------------------- the view


def chunk_hit_view(hit: Hit) -> dict[str, Any]:
    """The contract hit shape (CONTRACTS section 4): the reference chunk without ``index``."""
    row = {"position_int": hit.position_int, "page_dims_flt": hit.page_dims_flt, "table_features_with_weight": hit.table_features}
    out: dict[str, Any] = {
        "chunk_id": hit.chunk_id,
        "doc_id": hit.doc_id,
        "doc_name": hit.doc_name,
        "dataset_id": hit.dataset_id,
        "content": hit.content,
        **chunk_view_fields(row),
        "similarity": hit.similarity,
        "term_similarity": hit.term_similarity,
        "vector_similarity": hit.vector_similarity,
    }
    if hit.rerank_similarity is not None:
        out["rerank_similarity"] = hit.rerank_similarity
    return out


def _doc_aggs(hits: list[Hit]) -> list[dict[str, Any]]:
    counts = Counter(h.doc_id for h in hits)
    names = {h.doc_id: h.doc_name for h in hits}
    return [{"doc_id": doc_id, "doc_name": names[doc_id], "count": count} for doc_id, count in counts.most_common()]


# ----------------------------------------------------------------------------- the service


def search(
    principal: Principal,
    scope: ActingScope,
    body: Mapping[str, Any],
    settings: Settings,
    *,
    doc_store: DocStoreConnection | None = None,
    embedder: Embedder | None = None,
    reranker: Reranker | None = None,
) -> dict[str, Any]:
    """``{"total", "chunks", "doc_aggs", "rerank_applied", "timings"}`` for one question over one or more datasets of the acting workspace."""
    params = parse_body(body, settings)
    opened = _authorize(principal, scope, params["dataset_ids"])
    result = _run_retrieval(settings, scope.tenant_id, params, _one_model(opened), doc_store=doc_store, embedder=embedder, reranker=reranker)
    logger.info("retrieval done tenant=%s datasets=%s hits=%d", scope.tenant_id, ",".join(params["dataset_ids"]), len(result.hits))
    return sanitize_floats(
        {
            "total": int(result.total),
            "chunks": [chunk_hit_view(h) for h in result.hits],
            "doc_aggs": _doc_aggs(result.hits),
            "rerank_applied": result.rerank_applied,
            "timings": result.timings,
        }
    )


def retrieve_for_chat(
    settings: Settings,
    assistant: AssistantRecord,
    tenant_id: str,
    dataset_ids: list[str] | tuple[str, ...],
    question: str,
    *,
    doc_store: DocStoreConnection | None = None,
    embedder: Embedder | None = None,
) -> RetrievalResult:
    """Run the same search pipeline for an already authorised chat binding."""
    if not dataset_ids:
        raise _invalid("chat retrieval needs a dataset")
    with DB.connection_context():
        from api.db.models import Knowledgebase

        rows = list(Knowledgebase.select(Knowledgebase.id, Knowledgebase.embd_id).where((Knowledgebase.id.in_(dataset_ids)) & (Knowledgebase.tenant_id == tenant_id)))
    if len(rows) != len(dataset_ids):
        raise _not_found()
    models = {row.embd_id for row in rows}
    if len(models) != 1:
        raise _invalid("the datasets use different embedding models", reasons.EMBEDDING_MISMATCH)
    params = {
        "dataset_ids": list(dataset_ids),
        "question": question,
        "doc_ids": None,
        "similarity_threshold": assistant.similarity_threshold,
        "vector_similarity_weight": assistant.vector_similarity_weight,
        "top_k": settings.retrieval.top_k,
        "rerank_id": assistant.rerank_id or None,
        "fusion": "weighted_sum",
        "page": 1,
        "size": assistant.top_n,
    }
    return _run_retrieval(settings, tenant_id, params, models.pop(), doc_store=doc_store, embedder=embedder)


def _run_retrieval(
    settings: Settings,
    tenant_id: str,
    params: Mapping[str, Any],
    model_id: str,
    *,
    doc_store: DocStoreConnection | None = None,
    embedder: Embedder | None = None,
    reranker: Reranker | None = None,
) -> RetrievalResult:
    """Shared embed, search, prune and optional rerank pipeline."""
    rerank = _build_reranker(settings, tenant_id, params["rerank_id"], reranker)  # a bad model id costs no embedding call
    started = time.monotonic()
    vector = _embed_question(settings, tenant_id, model_id, params["question"], embedder)
    embed_ms = (time.monotonic() - started) * 1000.0
    request = RetrievalRequest(
        tenant_id=tenant_id,
        dataset_ids=params["dataset_ids"],
        question=params["question"],
        query_vector=vector,
        vector_dim=len(vector),
        doc_ids=params["doc_ids"],
        similarity_threshold=params["similarity_threshold"],
        vector_similarity_weight=params["vector_similarity_weight"],
        top_k=params["top_k"],
        fusion=params["fusion"],
        rerank_cap=settings.retrieval.rerank_max_candidates,
        page=params["page"],
        size=params["size"],
    )
    engine = doc_store if doc_store is not None else get_doc_store(settings)
    retriever = Retriever(engine, settings, SynonymSource(settings.redis, settings.retrieval))
    try:
        result = retriever.retrieve(request, document_exists=_documents_that_exist(params["dataset_ids"]), reranker=rerank)
    except DocStoreError as exc:
        logger.warning("retrieval could not read the index datasets=%s error=%s", ",".join(params["dataset_ids"]), type(exc).__name__)
        raise ServiceError(Kind.UNAVAILABLE, reasons.INDEX_UNAVAILABLE, "the search index is not available, try again shortly") from None
    return RetrievalResult(
        result.total,
        result.hits,
        result.rerank_applied,
        {"embed_ms": embed_ms, "search_ms": result.timings.get("search_ms", 0.0), "rerank_ms": result.timings.get("rerank_ms", 0.0)},
    )
