"""Retriever: two-stage hybrid search over the document-store port, scoring, pruning, rerank blend and RRF (plan 05-03).

Covers RETR-01, RETR-05, RETR-08, RETR-10, RETR-11, RETR-12, RETR-14, RETR-15 and TEN-03. Stage 1 asks the engine for a pool with one
text + kNN + weighted-sum search (the 0.001/1 weights make the engine order the pool by vector closeness, so a text-only match
still enters it). Stage 2 re-scores the pool with a kNN-only search so every candidate gets a cosine (R-195, ``2 * score - 1``).
The Retriever only reads: it never inserts, updates or deletes (D-22). Logs, if any, carry dataset ids and exception class names only.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from common.doc_store.doc_store_base import (
    DocStoreConnection,
    FusionExpr,
    MatchDenseExpr,
    index_name,
    vector_field,
)
from common.settings import RetrievalSettings
from rag.nlp.fusion import apply_threshold, cosine_from_es_score, fuse, paginate, rank_feature, rrf, token_overlap
from rag.nlp.query import QueryBuilder, QueryPlan
from rag.nlp.tokenizer import tokenize

logger = logging.getLogger(__name__)

SELECT_FIELDS = [
    "content_with_weight",
    "content_ltks",
    "title_tks",
    "docnm_kwd",
    "doc_id",
    "kb_id",
    "position_int",
    "page_num_int",
    "page_dims_flt",
    "pagerank_fea",
]
MAX_TOP_K = 10000
FUSIONS = ("weighted_sum", "rrf")

Reranker = Callable[[str, list[str]], list[float]]
DocumentExists = Callable[[set[str]], Iterable[str]]


@dataclass(frozen=True)
class RetrievalRequest:
    tenant_id: str
    dataset_ids: list[str]
    question: str
    query_vector: list[float]
    vector_dim: int
    doc_ids: list[str] | None = None
    similarity_threshold: float = 0.2
    vector_similarity_weight: float = 0.3
    top_k: int = 1024
    fusion: str = "weighted_sum"
    rerank_cap: int = 16
    page: int = 1
    size: int = 10

    def __post_init__(self) -> None:
        if not isinstance(self.question, str):
            raise ValueError("question must be a string")
        if not (0.0 <= self.similarity_threshold <= 1.0) or not (0.0 <= self.vector_similarity_weight <= 1.0):  # also false for NaN
            raise ValueError("similarity threshold and vector weight must be within [0, 1]")
        if not 1 <= self.top_k <= MAX_TOP_K or self.rerank_cap < 1 or self.page < 1 or self.size < 1:
            raise ValueError("top_k, rerank_cap, page and size are out of range")
        if self.fusion not in FUSIONS:
            raise ValueError("unknown fusion method")


@dataclass(frozen=True)
class Hit:
    chunk_id: str
    doc_id: str
    doc_name: str
    dataset_id: str
    content: str
    position_int: list[Any]
    page_num_int: list[Any]
    page_dims_flt: list[Any]
    similarity: float
    term_similarity: float
    vector_similarity: float
    rerank_similarity: float | None = None


@dataclass(frozen=True)
class RetrievalResult:
    total: int
    hits: list[Hit]
    rerank_applied: bool
    timings: dict[str, float] = field(default_factory=dict)


@dataclass
class _Candidate:
    row: dict[str, Any]
    order: float = 0.0  # pool order key (the RRF score; 0 for weighted_sum, where the sort is by similarity)
    tsim: float = 0.0
    vsim: float = 0.0
    sim: float = 0.0
    rerank: float | None = None


def _finite(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else 0.0


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


class Retriever:
    def __init__(self, doc_store: DocStoreConnection, settings: Any, synonyms: Any = None) -> None:
        # Accepts the retrieval section or the whole Settings object, so the service can pass what it has.
        self._store = doc_store
        self._settings: RetrievalSettings = getattr(settings, "retrieval", settings)
        self._builder = QueryBuilder(synonyms, self._settings)

    # --- public --------------------------------------------------------------------------------------------------
    def retrieve(self, request: RetrievalRequest, *, document_exists: DocumentExists | None = None, reranker: Reranker | None = None) -> RetrievalResult:
        started = time.monotonic()
        plan = self._builder.build(request.question)
        if plan.empty or request.doc_ids is not None and not request.doc_ids:
            return RetrievalResult(0, [], False, {"search_ms": 0.0, "rerank_ms": 0.0})
        pool = self._pool(request, plan)
        if document_exists is not None and pool:
            pool = self._prune(pool, document_exists)
        if pool:
            self._score(request, plan, pool)
        search_ms = (time.monotonic() - started) * 1000.0
        rerank_ms, applied = 0.0, False
        if reranker is not None and pool:
            started = time.monotonic()
            pool = self._rerank(request, pool, reranker)
            rerank_ms, applied = (time.monotonic() - started) * 1000.0, True
        hits, total = self._finish(request, pool, ordered_by_rrf=request.fusion == "rrf" and not applied)
        return RetrievalResult(total, hits, applied, {"search_ms": search_ms, "rerank_ms": rerank_ms})

    # --- stage 1 -------------------------------------------------------------------------------------------------
    @staticmethod
    def _must_not() -> dict[str, Any]:
        return {"removed_kwd": "Y"}

    def _condition(self, request: RetrievalRequest) -> dict[str, Any]:
        condition: dict[str, Any] = {"available_int": 1, "doc_enabled_int": 1}
        if request.doc_ids:
            condition["doc_id"] = list(request.doc_ids)
        condition["must_not"] = self._must_not()
        return condition

    def _search(self, request: RetrievalRequest, condition: dict[str, Any], matches: list[Any], limit: int, select: list[str]) -> list[dict[str, Any]]:
        result = self._store.search(
            select_fields=select,
            highlight_fields=[],
            condition=condition,
            match_expressions=matches,
            order_by=None,
            offset=0,
            limit=limit,
            index_names=index_name(request.tenant_id),
            dataset_ids=list(request.dataset_ids),
        )
        return result.hits

    def _dense(self, request: RetrievalRequest, top_k: int) -> MatchDenseExpr:
        return MatchDenseExpr(vector_field(request.vector_dim), list(request.query_vector), "float", "cosine", top_k, {"similarity": 0.0})

    def _text_hits(self, request: RetrievalRequest, plan: QueryPlan, extra: list[Any]) -> list[dict[str, Any]]:
        """Text-led search; one retry at the lower minimum-should-match when nothing came back."""
        condition = self._condition(request)
        for retry in (False, True):
            matches = [plan.text_expr(request.top_k, retry), *extra]
            hits = self._search(request, condition, matches, request.top_k, SELECT_FIELDS)
            if hits:
                return hits
        return []

    def _pool(self, request: RetrievalRequest, plan: QueryPlan) -> list[_Candidate]:
        dense = self._dense(request, request.top_k)
        if request.fusion == "rrf":
            return self._rrf_pool(request, plan, dense)
        # weights are text boost, then dense boost: the engine orders the pool by vector closeness (R-195)
        fusion = FusionExpr("weighted_sum", request.top_k, {"weights": "0.001,1"})
        return [_Candidate(row) for row in self._text_hits(request, plan, [dense, fusion])]

    def _rrf_pool(self, request: RetrievalRequest, plan: QueryPlan, dense: MatchDenseExpr) -> list[_Candidate]:
        text_rows = self._text_hits(request, plan, [])
        dense_rows = self._search(request, self._condition(request), [dense], request.top_k, SELECT_FIELDS)
        rows = {str(row["id"]): row for row in [*dense_rows, *text_rows]}
        scores = rrf([[str(r["id"]) for r in text_rows], [str(r["id"]) for r in dense_rows]])
        ordered = sorted(rows, key=lambda cid: scores[cid], reverse=True)
        return [_Candidate(rows[cid], order=scores[cid]) for cid in ordered[: request.top_k]]

    @staticmethod
    def _prune(pool: list[_Candidate], document_exists: DocumentExists) -> list[_Candidate]:
        wanted = {str(c.row.get("doc_id")) for c in pool}
        alive = {str(d) for d in document_exists(wanted)}
        return [c for c in pool if str(c.row.get("doc_id")) in alive]

    # --- stage 2 and scoring -------------------------------------------------------------------------------------
    def _score(self, request: RetrievalRequest, plan: QueryPlan, pool: list[_Candidate]) -> None:
        ids = [str(c.row["id"]) for c in pool]
        condition = {"id": ids, "must_not": self._must_not()}
        rescored = self._search(request, condition, [self._dense(request, len(ids))], len(ids), ["doc_id"])
        cosine = {str(row["id"]): cosine_from_es_score(_finite(row.get("_score"))) for row in rescored}
        weight = request.vector_similarity_weight
        for candidate in pool:
            row = candidate.row
            text = f"{row.get('content_ltks') or ''} {row.get('title_tks') or ''}"
            candidate.tsim = token_overlap(plan.tokens, tokenize(text))
            candidate.vsim = cosine.get(str(row["id"]), 0.0)
            candidate.sim = fuse(candidate.tsim, candidate.vsim, weight, rank_feature(None, _finite(row.get("pagerank_fea"))))

    def _rerank(self, request: RetrievalRequest, pool: list[_Candidate], reranker: Reranker) -> list[_Candidate]:
        best = sorted(pool, key=lambda c: c.sim, reverse=True)[: request.rerank_cap]
        scores = reranker(request.question, [str(c.row.get("content_with_weight") or "") for c in best])
        if not isinstance(scores, list) or len(scores) != len(best):
            raise ValueError("the reranker returned a different number of scores than texts")
        for candidate, score in zip(best, scores, strict=True):
            if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
                raise ValueError("the reranker returned a non-finite score")
            candidate.rerank = min(1.0, max(0.0, float(score)))
            fea = rank_feature(None, _finite(candidate.row.get("pagerank_fea")))
            candidate.sim = fuse(candidate.tsim, candidate.rerank, request.vector_similarity_weight, fea)
        return best

    # --- threshold, order, page ----------------------------------------------------------------------------------
    @staticmethod
    def _finish(request: RetrievalRequest, pool: list[_Candidate], *, ordered_by_rrf: bool) -> tuple[list[Hit], int]:
        kept = apply_threshold([(c, c.sim) for c in pool], request.similarity_threshold)
        if ordered_by_rrf:
            kept.sort(key=lambda pair: pair[0].order, reverse=True)  # stable: ties keep the similarity order
        page, total = paginate(kept, request.page, request.size)
        return [_to_hit(candidate) for candidate, _ in page], total


def _to_hit(candidate: _Candidate) -> Hit:
    row = candidate.row
    return Hit(
        chunk_id=str(row["id"]),
        doc_id=str(row.get("doc_id") or ""),
        doc_name=str(row.get("docnm_kwd") or ""),
        dataset_id=str(row.get("kb_id") or ""),
        content=str(row.get("content_with_weight") or ""),
        position_int=_list(row.get("position_int")),
        page_num_int=_list(row.get("page_num_int")),
        page_dims_flt=_list(row.get("page_dims_flt")),
        similarity=candidate.sim,
        term_similarity=candidate.tsim,
        vector_similarity=candidate.vsim,
        rerank_similarity=candidate.rerank,
    )
