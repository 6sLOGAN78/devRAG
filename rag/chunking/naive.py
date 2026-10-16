"""Naive chunker (CHUNK-02): cut at delimiter characters, merge units up to a token budget, repeat an overlap.

The delimiter string is a set of literal characters scanned linearly. It is never compiled as a regular expression
(T-04-06-01), so no user setting can cause catastrophic backtracking.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from rag.chunking.types import Chunk
from rag.nlp.token_count import count_tokens, split_at_tokens, tail_tokens
from rag.parsers.types import PageBox, ParsedBlock

MAX_OVERLAP_PERCENT = 50


@dataclass(frozen=True)
class NaiveConfig:
    chunk_token_num: int = 512
    delimiter: str = "\n!?;。；！？"
    overlapped_percent: int = 0


def split_units(text: str, delimiter: str) -> list[str]:
    """Cut after each delimiter character, keeping the delimiter with the unit before it."""
    marks = frozenset(delimiter)
    units: list[str] = []
    start = 0
    for i, ch in enumerate(text):
        if ch in marks:
            units.append(text[start : i + 1])
            start = i + 1
    if start < len(text):
        units.append(text[start:])
    return units


class _Builder:
    def __init__(self) -> None:
        self.text = ""
        self.boxes: list[PageBox] = []
        self.sizes: dict[int, tuple[float, float]] = {}
        self.fresh = False  # True once a real unit (not only an overlap tail) was added

    def add_meta(self, block: ParsedBlock) -> None:
        for box in block.boxes:
            if box not in self.boxes:
                self.boxes.append(box)
        self.sizes.update(block.page_sizes)


def chunk(blocks: Iterable[ParsedBlock], cfg: NaiveConfig) -> Iterator[Chunk]:
    limit = max(1, cfg.chunk_token_num)
    overlap = min(max(cfg.overlapped_percent, 0), MAX_OVERLAP_PERCENT)
    cur = _Builder()
    index = 0

    def emit(builder: _Builder, text: str) -> Chunk | None:
        nonlocal index
        if not text.strip():
            return None
        made = Chunk(text, tuple(builder.boxes), dict(builder.sizes), count_tokens(text), index)
        index += 1
        return made

    def restart(previous: str) -> _Builder:
        fresh = _Builder()
        if overlap:
            fresh.text = tail_tokens(previous, count_tokens(previous) * overlap // 100)
        return fresh

    for block in blocks:
        units = split_units(block.text, cfg.delimiter)
        if cur.fresh and cur.text and not cur.text[-1].isspace():
            cur.text += "\n"  # blocks are separate paragraphs
        for unit in units:
            if not unit.strip():
                if cur.fresh and count_tokens(cur.text + unit) <= limit:
                    cur.text += unit
                continue
            candidate = cur.text + unit
            if count_tokens(candidate) <= limit:
                cur.text = candidate
                cur.fresh = True
                cur.add_meta(block)
                continue
            if cur.fresh:
                made = emit(cur, cur.text)
                if made:
                    yield made
                cur = restart(cur.text)
            else:
                cur = _Builder()  # drop a lone overlap tail that would crowd out the unit
            candidate = cur.text + unit
            if count_tokens(candidate) <= limit:
                cur.text = candidate
                cur.fresh = True
                cur.add_meta(block)
                continue
            cur = _Builder()
            pieces = split_at_tokens(unit, limit)
            for piece in pieces[:-1]:
                solo = _Builder()
                solo.add_meta(block)
                made = emit(solo, piece)
                if made:
                    yield made
            cur.text = pieces[-1]
            cur.fresh = True
            cur.add_meta(block)
    if cur.fresh:
        made = emit(cur, cur.text)
        if made:
            yield made
