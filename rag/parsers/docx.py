"""DOCX parser (PARSE-09): body in document order, headings marked, tables as escaped HTML, images skipped (D-27)."""

from __future__ import annotations

import zipfile
from collections.abc import Iterator

import docx
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table
from docx.text.paragraph import Paragraph
from lxml import etree

from rag.parsers.errors import FileDamaged, NoReadableText
from rag.parsers.limits import check_ooxml_limits
from rag.parsers.tabletext import render_table
from rag.parsers.types import ParsedBlock, ParseLimits, ParseReport, SourceFile

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_DAMAGE = (zipfile.BadZipFile, KeyError, ValueError, AttributeError, PackageNotFoundError, etree.XMLSyntaxError, OSError)


def _is_heading(paragraph: Paragraph) -> bool:
    name = paragraph.style.name if paragraph.style is not None else ""
    return name == "Title" or name.startswith("Heading")


def _extract(source: SourceFile, report: ParseReport) -> list[ParsedBlock]:
    document = docx.Document(str(source.path))
    body = document.element.body
    blocks: list[ParsedBlock] = []
    for child in body.iterchildren():
        if child.tag == f"{_W}p":
            paragraph = Paragraph(child, document)
            text = paragraph.text.strip()
            if text:
                blocks.append(ParsedBlock(text, "heading" if _is_heading(paragraph) else "text"))
        elif child.tag == f"{_W}tbl":
            table = Table(child, document)
            rows = [[cell.text for cell in row.cells] for row in table.rows]
            if any(c.strip() for r in rows for c in r):
                blocks.append(ParsedBlock(render_table(rows), "table"))
    images = sum(1 for _ in body.iter(f"{_W}drawing", f"{_W}pict"))
    if images:
        report.images_skipped += images
        report.add_note(f"{images} embedded images were skipped")
    return blocks


def parse(
    source: SourceFile,
    report: ParseReport,
    *,
    page_range: tuple[int, int] | None = None,
    limits: ParseLimits | None = None,
) -> Iterator[ParsedBlock]:
    del page_range, limits
    check_ooxml_limits(source.path)
    try:
        blocks = _extract(source, report)
    except _DAMAGE:
        raise FileDamaged() from None
    if not blocks:
        raise NoReadableText()
    return iter(blocks)
