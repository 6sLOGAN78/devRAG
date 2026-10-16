"""TXT, Markdown, CSV and JSON parser (D-13, D-28): decode, then split on blank lines."""

from __future__ import annotations

import re
from collections.abc import Iterator

import charset_normalizer

from rag.parsers.errors import FileDamaged, FileTooLarge, NoReadableText
from rag.parsers.types import ParsedBlock, ParseLimits, ParseReport, SourceFile

_BLANK_LINES = re.compile(r"\n[ \t]*\n(?:[ \t]*\n)*")


def _read(source: SourceFile, limit: int) -> bytes:
    try:
        with source.path.open("rb") as handle:
            data = handle.read(limit + 1)
    except OSError as exc:
        raise FileDamaged() from exc
    if len(data) > limit:
        raise FileTooLarge()
    return data


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    best = charset_normalizer.from_bytes(data).best()
    if best is None:
        raise FileDamaged()
    return str(best)


def parse(
    source: SourceFile,
    report: ParseReport,
    *,
    page_range: tuple[int, int] | None = None,
    limits: ParseLimits | None = None,
) -> Iterator[ParsedBlock]:
    del page_range  # honoured by PDF only
    limits = limits or ParseLimits()
    data = _read(source, limits.max_text_bytes)
    if not data.strip():
        raise NoReadableText()
    text = _decode(data).replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [p.strip() for p in _BLANK_LINES.split(text)]
    paragraphs = [p for p in paragraphs if p]
    if not paragraphs:
        raise NoReadableText()
    report.pages_total = None
    return iter([ParsedBlock(p) for p in paragraphs])
