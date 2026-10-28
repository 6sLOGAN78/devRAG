"""The chunker contract (D-17): every chunker yields ``Chunk``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from rag.parsers.types import PageBox
from rag.parsers.tables import Table


@dataclass(frozen=True)
class Chunk:
    text: str
    positions: tuple[PageBox, ...]
    page_sizes: Mapping[int, tuple[float, float]]
    token_num: int
    index: int
    tables: tuple[Table, ...] = ()
    image_ids: tuple[str, ...] = ()
    source_lines: tuple[tuple[int, int], ...] = ()
