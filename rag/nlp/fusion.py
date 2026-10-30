"""Retrieval arithmetic: hybrid fusion, rank feature, RRF, threshold, pagination, float sanitising.

Covers RETR-06 (weighted hybrid score), RETR-07 (reciprocal rank fusion, k = 60), RETR-13 (rank feature), RETR-14
(similarity threshold), RETR-15 (pagination window) and RETR-19 (NaN and Infinity become null). Decision R-195 fixes the
meaning of ``vector_weight``: it is the share of the vector similarity, so
``score = (1 - w) * term + w * vector + rank_feature``. Pure functions, no I/O.
"""

from __future__ import annotations

import math

RRF_K = 60


def fuse(tsim: float, vsim: float, vector_weight: float, rank_fea: float = 0.0) -> float:
    """Hybrid score: ``(1 - w) * tsim + w * vsim + rank_fea`` with ``w`` the vector share in [0, 1]."""
    if not (0.0 <= vector_weight <= 1.0):  # also false for NaN
        raise ValueError("vector_weight must be within [0, 1]")
    return (1.0 - vector_weight) * tsim + vector_weight * vsim + rank_fea


def cosine_from_es_score(score: float) -> float:
    """Elasticsearch scores a cosine kNN hit as ``(1 + cos) / 2``; map it back to ``cos`` clamped to [0, 1]."""
    if not math.isfinite(score):
        return 0.0
    return min(1.0, max(0.0, 2.0 * score - 1.0))


def token_overlap(query_tokens: list[str] | tuple[str, ...], doc_tokens: list[str] | tuple[str, ...]) -> float:
    """``|Q intersect D| / |Q|`` over the de-duplicated query tokens; 0.0 when the query has none."""
    query = set(query_tokens)
    if not query:
        return 0.0
    return len(query & set(doc_tokens)) / len(query)


def rank_feature(tag_score: float | None, pagerank: float | None) -> float:
    """``10 * tag_score + pagerank``; a missing value counts as 0."""
    return 10.0 * (tag_score or 0.0) + (pagerank or 0.0)


def rrf(rankings: list[list[str]], k: int = RRF_K) -> dict[str, float]:
    """Reciprocal rank fusion: ``sum(1 / (k + rank))`` with the rank starting at 1 in each ranking."""
    out: dict[str, float] = {}
    for ranking in rankings:
        for position, item in enumerate(ranking, start=1):
            out[item] = out.get(item, 0.0) + 1.0 / (k + position)
    return out


def apply_threshold[T](scored: list[tuple[T, float]], threshold: float) -> list[tuple[T, float]]:
    """Keep ``score >= threshold`` and sort descending; the sort is stable so ties keep their input order."""
    kept = [pair for pair in scored if math.isfinite(pair[1]) and pair[1] >= threshold]
    kept.sort(key=lambda pair: pair[1], reverse=True)
    return kept


def paginate[T](items: list[T], page: int, size: int) -> tuple[list[T], int]:
    """Return the ``[(page - 1) * size : page * size]`` window and the total of the input."""
    if page < 1 or size < 1:
        raise ValueError("page and size must be at least 1")
    start = (page - 1) * size
    return list(items[start : start + size]), len(items)


def sanitize_floats[T](obj: T) -> T:
    """Replace NaN and +/-Infinity with ``None`` in nested dicts, lists and tuples (returns a copy)."""
    # The return type is the input's shape with floats possibly replaced by None; callers treat it as the same container.
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None  # type: ignore[return-value]
    if isinstance(obj, dict):
        return {key: sanitize_floats(value) for key, value in obj.items()}  # type: ignore[return-value]
    if isinstance(obj, list):
        return [sanitize_floats(value) for value in obj]  # type: ignore[return-value]
    if isinstance(obj, tuple):
        return tuple(sanitize_floats(value) for value in obj)  # type: ignore[return-value]
    return obj


def tag_cosine(query: dict[str, float], source: dict[str, float]) -> float:
    """Cosine of complete tag vectors, with missing/zero vectors contributing zero."""
    from rag.parsers.tags import normalize_tags

    query, source = normalize_tags(query, limit=8192), normalize_tags(source)
    return min(1.0, max(0.0, sum(weight * source.get(label, 0.0) for label, weight in query.items())))
