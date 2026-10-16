"""The parser contract (D-17): every parser yields ``ParsedBlock`` from one ``parse`` entry point.

Every parser module exposes ``parse(source, report, *, page_range=None, limits=None) -> Iterator[ParsedBlock]``.
``page_range`` is 0-based, start inclusive and end exclusive, and only the PDF parser honours it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

BLOCK_KINDS = frozenset({"text", "heading", "table", "slide", "sheet"})
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

    def __post_init__(self) -> None:
        if self.kind not in BLOCK_KINDS:
            raise ValueError("unknown block kind")


@dataclass
class ParseReport:
    """Counters a parser fills while it runs; the worker stores them as the parse summary."""

    pages_total: int | None = None
    pages_without_text: int = 0
    images_skipped: int = 0
    notes: list[str] = field(default_factory=list)

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
