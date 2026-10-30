"""The chunker contract (D-17): every chunker yields ``Chunk``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from rag.parsers.types import PageBox
from rag.parsers.tables import Table
from rag.parsers.sections import Section
from rag.parsers.slides import Slide
from rag.parsers.audio_segments import AudioSpan
from rag.parsers.tags import TagFeature


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
    question: str = ""
    sections: tuple[Section, ...] = ()
    slide: Slide | None = None
    audio: AudioSpan | None = None
    tags: tuple[TagFeature, ...] = ()
