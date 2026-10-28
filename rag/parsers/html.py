"""HTML parser (PARSE-12): text only, scripts, styles, templates and comments removed."""

from __future__ import annotations

from collections.abc import Iterator

from bs4 import BeautifulSoup, Comment, Tag

from rag.parsers.errors import FileDamaged, FileTooLarge, NoReadableText
from rag.parsers.txt import _decode
from rag.parsers.types import ParsedBlock, ParseLimits, ParseReport, SourceFile

_DROP = ("script", "style", "noscript", "template", "head")
_HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_BLOCKS = [*sorted(_HEADINGS), "p", "li", "pre", "blockquote", "tr"]
_BLOCK_SET = frozenset(_BLOCKS)


def _text(tag: Tag) -> str:
    return " ".join(tag.get_text(" ", strip=True).split())


def _has_block_child(tag: Tag) -> bool:
    return tag.name not in ("tr", "pre") and tag.find(_BLOCKS) is not None


def parse(
    source: SourceFile,
    report: ParseReport,
    *,
    page_range: tuple[int, int] | None = None,
    limits: ParseLimits | None = None,
) -> Iterator[ParsedBlock]:
    del page_range
    limits = limits or ParseLimits()
    try:
        with source.path.open("rb") as handle:
            data = handle.read(limits.max_text_bytes + 1)
    except OSError:
        raise FileDamaged() from None
    if len(data) > limits.max_text_bytes:
        raise FileTooLarge()
    return iter(parse_markup(data))


def parse_markup(data: bytes) -> list[ParsedBlock]:
    """Inert bounded-by-caller markup extraction, shared with EPUB members."""
    markup = _decode(data)
    soup = BeautifulSoup(markup, "lxml")
    for node in soup.find_all(string=lambda s: isinstance(s, Comment)):
        node.extract()
    for tag in soup.find_all(_DROP):
        tag.decompose()
    blocks: list[ParsedBlock] = []
    consumed: set[int] = set()
    for tag in soup.find_all(_BLOCKS):
        if any(id(parent) in consumed for parent in tag.parents):
            continue
        if tag.name == "tr":
            consumed.add(id(tag))
            text = "\t".join(t for t in (_text(c) for c in tag.find_all(["td", "th"])) if t)
        elif _has_block_child(tag):
            continue
        else:
            text = _text(tag)
        if text:
            level = int(tag.name[1]) if tag.name in _HEADINGS else 0
            blocks.append(ParsedBlock(text, "heading" if level else "text", heading_level=level))
    if not blocks:
        fallback = _text(soup)
        if fallback:
            blocks.append(ParsedBlock(fallback))
    if not blocks:
        raise NoReadableText()
    return blocks
