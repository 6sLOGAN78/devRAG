"""Bounded Markdown blocks; source code and resource descriptors remain literal."""

from __future__ import annotations

import re
from collections.abc import Iterator

from rag.parsers.errors import FileTooLarge, NoReadableText
from rag.parsers.txt import _read, _decode
from rag.parsers.types import ParsedBlock, ParseLimits, ParseReport, SourceFile

MAX_LINE_CHARS = 262144
MAX_LINES = 1_000_000
MAX_BLOCKS = 100000
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})([^\n]*)$")
_ATX = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+|$)")
_SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
_LIST = re.compile(r"^ {0,3}(?:[-+*]|[0-9]{1,9}[.)])[ \t]+")
_CELL = re.compile(r"^:?-{3,}:?$")


def _table_rule(line: str) -> bool:
    cells = line.strip().strip("|").split("|")
    return bool(cells) and all(_CELL.fullmatch(cell.strip()) for cell in cells)


def parse(source: SourceFile, report: ParseReport, *, page_range=None, limits: ParseLimits | None = None) -> Iterator[ParsedBlock]:
    del page_range
    limits = limits or ParseLimits()
    text = _decode(_read(source, limits.max_text_bytes)).replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        raise NoReadableText()
    lines = text.splitlines(keepends=True)
    if len(lines) > MAX_LINES or any(len(line) > MAX_LINE_CHARS for line in lines):
        raise FileTooLarge()
    blocks = []
    index = 0

    def structural(at: int) -> bool:
        line = lines[at].rstrip("\n")
        return bool(
            _FENCE.match(line)
            or _ATX.match(line)
            or _LIST.match(line)
            or line.lstrip().startswith("![")
            or (at + 1 < len(lines) and (_SETEXT.fullmatch(lines[at + 1].rstrip("\n")) or ("|" in line and _table_rule(lines[at + 1]))))
        )

    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue
        first = index
        line = lines[index].rstrip("\n")
        fence = _FENCE.fullmatch(line)
        heading = _ATX.match(line)
        level = 0
        if fence and not (fence[1][0] == "`" and "`" in fence[2]):
            kind = "code"
            index += 1
            closed = False
            while index < len(lines):
                end = lines[index].rstrip("\n").rstrip(" \t")
                indentation = len(end) - len(end.lstrip(" "))
                end = end[indentation:]
                index += 1
                if indentation <= 3 and len(end) >= len(fence[1]) and set(end) == {fence[1][0]}:
                    closed = True
                    break
            if not closed:
                report.add_note("A Markdown code fence is not closed.")
        elif heading:
            kind, level = "heading", len(heading[1])
            index += 1
        elif index + 1 < len(lines) and _SETEXT.fullmatch(lines[index + 1].rstrip("\n")):
            kind, level = "heading", (1 if lines[index + 1].lstrip().startswith("=") else 2)
            index += 2
        elif index + 1 < len(lines) and "|" in line and _table_rule(lines[index + 1]):
            kind = "table"
            index += 2
            while index < len(lines) and lines[index].strip() and "|" in lines[index] and not (_ATX.match(lines[index]) or _FENCE.match(lines[index].rstrip("\n"))):
                index += 1
        elif line.lstrip().startswith("!["):
            kind = "image"
            report.images_skipped += 1  # Descriptor is retained; no resource is fetched or decoded.
            index += 1
        elif _LIST.match(line):
            kind = "list"
            index += 1
            while index < len(lines) and lines[index].strip() and (_LIST.match(lines[index]) or lines[index].startswith((" ", "\t"))):
                index += 1
        else:
            kind = "text"
            index += 1
            while index < len(lines) and lines[index].strip() and not structural(index):
                index += 1
        blocks.append(ParsedBlock("".join(lines[first:index]), kind, heading_level=level, line_range=(first + 1, index)))
        if len(blocks) > MAX_BLOCKS:
            raise FileTooLarge()
    report.pages_total = None
    return iter(blocks)
