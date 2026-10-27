"""DOCX parser (PARSE-09): body in document order, headings marked, tables as escaped HTML, configured remote image extraction; legacy skips counted (D-27)."""

from __future__ import annotations

import zipfile
from collections.abc import Iterator

import docx
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table
from docx.text.paragraph import Paragraph
from lxml import etree

from common.settings import Settings
from rag.parsers.errors import FileDamaged, NoReadableText
from rag.parsers.limits import check_ooxml_limits
from rag.parsers.ooxml_images import OOXMLImages
from rag.parsers.tabletext import render_table
from rag.parsers.types import ParsedBlock, ParseLimits, ParseReport, SourceFile

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_DAMAGE = (zipfile.BadZipFile, KeyError, ValueError, AttributeError, PackageNotFoundError, etree.XMLSyntaxError, OSError)


def _is_heading(paragraph: Paragraph) -> bool:
    name = paragraph.style.name if paragraph.style is not None else ""
    return name == "Title" or name.startswith("Heading")


def _extract(source: SourceFile, report: ParseReport, settings: Settings | None = None) -> list[ParsedBlock]:
    document = docx.Document(str(source.path))
    body = document.element.body
    blocks: list[ParsedBlock] = []
    with OOXMLImages(source.path, settings) as images:
        for child in body.iterchildren():
            assets = images.for_element(child, "word/document.xml")
            if child.tag == f"{_W}p":
                paragraph = Paragraph(child, document)
                text = paragraph.text.strip()
                if text or assets:
                    blocks.append(ParsedBlock(text, "heading" if _is_heading(paragraph) else "text", assets=assets))
            elif child.tag == f"{_W}tbl":
                table = Table(child, document)
                rows = [[cell.text for cell in row.cells] for row in table.rows]
                if any(c.strip() for r in rows for c in r) or assets:
                    blocks.append(ParsedBlock(render_table(rows), "table", assets=assets))
        if not images.enabled:
            skipped = sum(1 for _ in body.iter(f"{_W}drawing", f"{_W}pict"))
            if skipped:
                report.images_skipped += skipped
                report.add_note(f"{skipped} embedded images were skipped")
    return blocks


def parse(
    source: SourceFile,
    report: ParseReport,
    *,
    page_range: tuple[int, int] | None = None,
    limits: ParseLimits | None = None,
    settings: Settings | None = None,
) -> Iterator[ParsedBlock]:
    del page_range, limits
    check_ooxml_limits(source.path)
    try:
        blocks = _extract(source, report, settings)
    except _DAMAGE:
        raise FileDamaged() from None
    if not blocks:
        raise NoReadableText()
    return iter(blocks)
