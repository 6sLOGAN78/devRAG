"""Reference views and citation fallback for a completed chat turn."""
from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any

from api.db.services.retrieval_service import chunk_hit_view
from common.doc_store.doc_store_base import DocStoreError, index_name, vector_field
from rag.nlp.fusion import sanitize_floats
from rag.prompts.citations import insert_citations, valid_indices
from rag.utils.es_conn import get_doc_store

if TYPE_CHECKING:
    from api.db.services.chat_turn_service import TurnPlan
    from rag.nlp.search import Hit


def reference(chunks: tuple[Hit, ...], selected: set[int] | None = None) -> dict[str, Any]:
    """Keep prompt indices stable even when a stopped turn cites a sparse subset."""
    entries = [dict(index=index, **chunk_hit_view(hit)) for index, hit in enumerate(chunks) if selected is None or index in selected]
    counts = Counter(entry["doc_id"] for entry in entries)
    names = {entry["doc_id"]: entry["doc_name"] for entry in entries}
    return sanitize_floats({
        "chunks": entries,
        "doc_aggs": [{"doc_id": doc_id, "doc_name": names[doc_id], "count": count} for doc_id, count in counts.items()],
    })


def insert_missing(plan: TurnPlan, answer: str) -> tuple[str, bool]:
    """Fetch retained chunk vectors once and embed answer sentences only when no valid marker exists."""
    if not answer.strip() or not plan.used_chunks or valid_indices(answer, len(plan.used_chunks)) or plan.used_embedder is None:
        return answer, False
    dimension = plan.used_embedder.expected_dimension
    if dimension is None:
        return answer, False
    field = vector_field(dimension)
    ids = [hit.chunk_id for hit in plan.used_chunks]
    try:
        found = get_doc_store(plan.settings).search(
            select_fields=[field], highlight_fields=[], condition={"id": ids}, match_expressions=[], order_by=None,
            offset=0, limit=len(ids), index_names=index_name(plan.tenant_id), dataset_ids=list(plan.dataset_ids),
        )
    except DocStoreError:
        return answer, False
    vectors_by_id = {row.get("id"): row.get(field) for row in found.hits}
    vectors = {index: vectors_by_id[hit.chunk_id] for index, hit in enumerate(plan.used_chunks) if isinstance(vectors_by_id.get(hit.chunk_id), list)}
    result = insert_citations(answer, vectors, lambda sentences: plan.used_embedder.encode(sentences)[0])
    return result.text, result.inserted
