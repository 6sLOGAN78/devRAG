"""Read-time reference filtering for chat sessions (D-10, plan 05-09)."""
from __future__ import annotations

from typing import Any

from api.db.services.dialog_datasets import live_datasets, openable

_USER_FIELDS = frozenset({"id", "role", "content", "created_at"})
_ASSISTANT_FIELDS = _USER_FIELDS | {"reference", "finish", "usage", "latency_ms", "empty", "feedback"}
_CHUNK_FIELDS = frozenset({
    "index", "chunk_id", "doc_id", "doc_name", "dataset_id", "content", "positions", "page_sizes",
    "similarity", "term_similarity", "vector_similarity", "rerank_similarity",
})
_DOC_FIELDS = frozenset({"doc_id", "doc_name", "count"})


def redact_messages(messages: list[dict[str, Any]], tenant_id: str, user_id: str) -> list[dict[str, Any]]:
    """Build explicit public views; never mutate stored JSON or expose later-private chunks."""
    ids = {
        chunk["dataset_id"]
        for message in messages
        if isinstance(message.get("reference"), dict)
        for chunk in (message["reference"].get("chunks") or [])
        if isinstance(chunk, dict) and isinstance(chunk.get("dataset_id"), str)
    }
    known = live_datasets(ids)
    visible = {key for key in ids if key in known and openable(known[key], tenant_id, user_id)}
    result: list[dict[str, Any]] = []
    for message in messages:
        allowed = _ASSISTANT_FIELDS if message.get("role") == "assistant" else _USER_FIELDS
        copy = {key: message[key] for key in allowed if key in message and key != "reference"}
        reference = message.get("reference")
        if message.get("role") == "assistant" and isinstance(reference, dict):
            chunks = []
            visible_doc_ids: set[str] = set()
            for chunk in reference.get("chunks") or []:
                if not isinstance(chunk, dict):
                    continue
                if chunk.get("dataset_id") in visible:
                    chunks.append({key: chunk[key] for key in _CHUNK_FIELDS if key in chunk})
                    if isinstance(chunk.get("doc_id"), str):
                        visible_doc_ids.add(chunk["doc_id"])
                else:
                    chunks.append({"index": chunk.get("index"), "unavailable": True})
            doc_aggs = [
                {key: agg[key] for key in _DOC_FIELDS if key in agg}
                for agg in reference.get("doc_aggs") or []
                if isinstance(agg, dict) and agg.get("doc_id") in visible_doc_ids
            ]
            copy["reference"] = {"chunks": chunks, "doc_aggs": doc_aggs}
        result.append(copy)
    return result
