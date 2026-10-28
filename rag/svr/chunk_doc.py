"""Chunk ids, vector normalisation and the stored chunk row (CHUNK-16, IDX-01..03, IDX-07, R-155, D-26).

Parsed ids are ``{doc_id}_{from_page*1000+i}`` with ``0 <= i < 1000 * (to_page - from_page)``: a retried or reclaimed task writes the same ids, and tasks
of different page ranges never collide. A single-task non-PDF document spans 1,000,000 pages, so its chunk count is effectively unbounded.
Hand-added chunks use ``{doc_id}_m_{uuid4 hex}``, a grammar that never matches a parsed id.
"""

from __future__ import annotations

import datetime
import json
import math
import uuid
from typing import Any

from common.doc_store.doc_store_base import vector_field
from rag.chunking.types import Chunk
from rag.nlp.tokenizer import fine_grained_tokenize, tokenize
from rag.parsers.table_features import MAX_TABLE_FEATURE_BYTES, TABLE_FIELD
from rag.svr.failure import TaskFailure

PAGE_STRIDE = 1000
ORIGIN_PARSED = "parsed"
ORIGIN_EDITED = "edited"
ORIGIN_MANUAL = "manual"
MANUAL_ORDER = 2_000_000_000  # sorts after every parsed chunk (parsed order_int stays below 1000 * 1,000,000 pages)


def parsed_chunk_id(doc_id: str, from_page: int, i: int, to_page: int) -> str:
    if i < 0 or i >= PAGE_STRIDE * max(to_page - from_page, 0):
        raise TaskFailure("chunk", "too_many_chunks")
    return f"{doc_id}_{from_page * PAGE_STRIDE + i}"


def manual_chunk_id(doc_id: str) -> str:
    return f"{doc_id}_m_{uuid.uuid4().hex}"


def l2_normalize(vector: list[float]) -> list[float]:
    """Unit-length copy. A zero or non-finite vector is refused as a provider fault (T-04-11-05)."""
    norm = math.sqrt(sum(x * x for x in vector)) if all(math.isfinite(x) for x in vector) else float("nan")
    if not math.isfinite(norm) or norm == 0.0:
        raise TaskFailure("embed", "provider_refused")
    return [x / norm for x in vector]


def _stem(name: str) -> str:
    return name.rsplit(".", 1)[0] if "." in name else name


def build_row(
    chunk: Chunk,
    *,
    index: int,
    doc_id: str,
    kb_id: str,
    doc_name: str,
    task_id: str,
    from_page: int,
    to_page: int,
    vector: list[float],
    enabled: bool,
    now: datetime.datetime | None = None,
) -> dict[str, Any]:
    chunk_id = parsed_chunk_id(doc_id, from_page, index, to_page)
    moment = now or datetime.datetime.now()
    title = _stem(doc_name)
    boxes = chunk.positions
    pages = sorted({int(box.page) for box in boxes})
    features = {}
    if chunk.image_ids:
        features["image_ids_kwd"] = list(chunk.image_ids)
    if chunk.tables:
        encoded = json.dumps([table.to_dto() for table in chunk.tables], ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode()) > MAX_TABLE_FEATURE_BYTES or len(chunk.tables) > 16:
            raise TaskFailure("chunk", "file_too_large")
        features[TABLE_FIELD] = encoded
    return {
        **features,
        "id": chunk_id,
        "doc_id": doc_id,
        "kb_id": kb_id,
        "docnm_kwd": doc_name,
        "content_with_weight": chunk.text,
        "content_ltks": " ".join(tokenize(chunk.text)),
        "content_sm_ltks": " ".join(fine_grained_tokenize(chunk.text)),
        "title_tks": " ".join(tokenize(title)),
        "title_sm_tks": " ".join(fine_grained_tokenize(title)),
        "position_int": [[int(b.page), int(b.x0), int(b.top), int(b.x1), int(b.bottom)] for b in boxes],
        "page_num_int": pages,
        "top_int": int(boxes[0].top) if boxes else 0,
        "available_int": 1,
        vector_field(len(vector)): vector,
        "create_time": moment.strftime("%Y-%m-%d %H:%M:%S"),
        "create_timestamp_flt": moment.timestamp(),
        "order_int": from_page * PAGE_STRIDE + index,
        "task_id": task_id,
        "origin_kwd": ORIGIN_PARSED,
        "token_num_int": int(chunk.token_num),
        "doc_enabled_int": 1 if enabled else 0,
        "page_dims_flt": [[float(p), float(w), float(h)] for p, (w, h) in sorted(chunk.page_sizes.items())],
    }


def manual_row(
    text: str,
    *,
    doc_id: str,
    kb_id: str,
    doc_name: str,
    vector: list[float],
    enabled: bool,
    token_num: int,
    now: datetime.datetime | None = None,
) -> dict[str, Any]:
    """The stored row of a hand-added chunk: no geometry, ``origin_kwd`` manual, ``order_int`` last, a ``{doc_id}_m_{uuid}`` id (R-155)."""
    chunk = Chunk(text=text, positions=(), page_sizes={}, token_num=token_num, index=0)
    row = build_row(chunk, index=0, doc_id=doc_id, kb_id=kb_id, doc_name=doc_name, task_id="", from_page=0, to_page=1, vector=vector, enabled=enabled, now=now)
    row["id"] = manual_chunk_id(doc_id)
    row["order_int"] = MANUAL_ORDER
    row["origin_kwd"] = ORIGIN_MANUAL
    return row
