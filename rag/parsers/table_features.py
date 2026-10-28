"""Explicit bounded public table features; never expose native bytes or internal digests."""

from __future__ import annotations

import json

from rag.parsers.tables import Table

TABLE_FIELD = "table_features_with_weight"
MAX_TABLE_FEATURE_BYTES = 1024 * 1024


def table_views(raw: object) -> list[dict]:
    if not isinstance(raw, list) or len(raw) > 16:
        return []
    try:
        return [Table.from_dto(item).to_dto() for item in raw]
    except (TypeError, ValueError, KeyError, AttributeError):
        return []


def tables_of(row) -> list[dict]:
    raw = row.get(TABLE_FIELD)
    if not isinstance(raw, str) or len(raw.encode()) > MAX_TABLE_FEATURE_BYTES:
        return []
    try:
        return table_views(json.loads(raw))
    except (ValueError, RecursionError):
        return []
