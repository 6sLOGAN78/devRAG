"""The parser contract (D-17): every parser yields ``ParsedBlock`` from one ``parse`` entry point.

Every parser module exposes ``parse(source, report, *, page_range=None, limits=None) -> Iterator[ParsedBlock]``.
``page_range`` is 0-based, start inclusive and end exclusive, and only the PDF parser honours it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, get_args

from rag.parsers.assets import ParsedAsset
from rag.parsers.tables import Table
from rag.parsers.records import Record
from rag.parsers.sections import Section
from rag.parsers.slides import Slide
from rag.parsers.audio_segments import AudioSpan

BLOCK_KINDS = frozenset({"text", "heading", "table", "slide", "sheet", "code", "list", "image", "audio"})
LayoutLabel = Literal["_background_", "Text", "Title", "Figure", "Figure caption", "Table", "Table caption", "Header", "Footer", "Reference", "Equation"]
LAYOUT_LABELS = get_args(LayoutLabel)
MAX_NOTES = 200


@dataclass(frozen=True)
class PageBox:
    """A rectangle on a page, in page units."""

    page: int
    x0: float
    top: float
    x1: float
    bottom: float


@dataclass(frozen=True)
class ParsedBlock:
    text: str
    kind: str = "text"
    boxes: tuple[PageBox, ...] = ()
    page_sizes: dict[int, tuple[float, float]] = field(default_factory=dict)

    layout_label: LayoutLabel | None = None
    assets: tuple[ParsedAsset, ...] = ()
    table: Table | None = None
    image_ids: tuple[str, ...] = ()
    heading_level: int = 0
    line_range: tuple[int, int] | None = None
    record: Record | None = None
    section: Section | None = None
    slide: Slide | None = None
    audio: AudioSpan | None = None

    def __post_init__(self) -> None:
        if type(self.heading_level) is not int or not 0 <= self.heading_level <= 6:
            raise ValueError("invalid heading level")
        if self.line_range is not None and (len(self.line_range) != 2 or any(type(v) is not int for v in self.line_range) or not 1 <= self.line_range[0] <= self.line_range[1] <= 1_000_000):
            raise ValueError("invalid source lines")
        if self.layout_label is not None and self.layout_label not in LAYOUT_LABELS:
            raise ValueError("unknown layout label")
        if self.kind not in BLOCK_KINDS:
            raise ValueError("unknown block kind")


@dataclass
class ParseReport:
    """Counters a parser fills while it runs; the worker stores them as the parse summary."""

    pages_total: int | None = None
    pages_without_text: int = 0
    images_skipped: int = 0
    notes: list[str] = field(default_factory=list)
    layout_backend: str | None = None
    layout_regions: int = 0

    def add_note(self, sentence: str) -> None:
        if len(self.notes) < MAX_NOTES:
            self.notes.append(sentence)


@dataclass(frozen=True)
class SourceFile:
    path: Path
    suffix: str
    size: int


@dataclass(frozen=True)
class ParseLimits:
    max_text_bytes: int = 104857600
    max_pages: int = 20000
    xlsx_max_cells: int = 1000000
