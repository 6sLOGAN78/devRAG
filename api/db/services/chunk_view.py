"""Positions and page sizes of a stored chunk row, shared by the chunk list and the retrieval view (plan 05-04; CHUNK-16, RETR-17).

``position_int`` is stored either nested (``[[page, x0, top, x1, bottom], ...]``) or flat with stride five; both read the same. ``page_dims_flt``
holds ``[page, width, height]`` entries. Nothing here touches a database or a framework.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from rag.parsers.slides import slide_of
from rag.parsers.table_features import TABLE_FIELD, tables_of

POSITION_STRIDE = 5
_DIMS_ENTRY = 3


def _raw_boxes(raw: object) -> list[list[Any]]:
    if not isinstance(raw, list) or not raw:
        return []
    if isinstance(raw[0], (list, tuple)):
        return [list(r) for r in raw if isinstance(r, (list, tuple)) and len(r) == POSITION_STRIDE]
    return [raw[i : i + POSITION_STRIDE] for i in range(0, len(raw) - POSITION_STRIDE + 1, POSITION_STRIDE)]


def positions_of(row: Mapping[str, Any]) -> list[dict[str, int]]:
    """Boxes from the row's ``position_int`` in either stored shape."""
    return [{"page": int(r[0]), "x0": int(r[1]), "top": int(r[2]), "x1": int(r[3]), "bottom": int(r[4])} for r in _raw_boxes(row.get("position_int"))]


def page_sizes_of(row: Mapping[str, Any], wanted: set[int] | None = None) -> dict[str, list[float]]:
    """``{"<page>": [width, height]}`` from the row's ``page_dims_flt``; by default only the pages the row's own boxes use."""
    pages = wanted if wanted is not None else {p["page"] for p in positions_of(row)}
    sizes: dict[str, list[float]] = {}
    for entry in row.get("page_dims_flt") or []:
        if isinstance(entry, (list, tuple)) and len(entry) == _DIMS_ENTRY and int(entry[0]) in pages:
            sizes[str(int(entry[0]))] = [float(entry[1]), float(entry[2])]
    return sizes


def merge_page_sizes(parts: Iterable[Mapping[str, list[float]]]) -> dict[str, list[float]]:
    """Union of several page-size maps, ordered by page number."""
    merged: dict[str, list[float]] = {}
    for part in parts:
        merged.update(part)
    return dict(sorted(merged.items(), key=lambda kv: int(kv[0])))


def chunk_view_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    """The two location keys of one chunk view."""
    slide = slide_of(row)
    return {**({"slide": slide} if slide else {}), "positions": positions_of(row), "page_sizes": page_sizes_of(row), **({"tables": tables_of(row)} if row.get(TABLE_FIELD) else {})}
