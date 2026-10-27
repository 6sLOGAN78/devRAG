"""PPTX parser (PARSE-11): one slide block per slide, configured remote figures; legacy skips counted (D-27)."""

from __future__ import annotations

import zipfile
from collections.abc import Iterator

import pptx
from lxml import etree
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.exc import PackageNotFoundError

from common.settings import Settings
from rag.parsers.errors import FileDamaged, NoReadableText
from rag.parsers.limits import check_ooxml_limits
from rag.parsers.ooxml_images import OOXMLImages
from rag.parsers.types import ParsedBlock, ParseLimits, ParseReport, SourceFile

_DAMAGE = (zipfile.BadZipFile, KeyError, ValueError, AttributeError, PackageNotFoundError, etree.XMLSyntaxError, OSError)


def _shape_lines(shapes, skip_id: int | None, lines: list[str]) -> int:
    images = 0
    for shape in shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            images += _shape_lines(shape.shapes, skip_id, lines)
        elif shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
            images += 1
        elif getattr(shape, "has_table", False) and shape.has_table:
            for row in shape.table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    lines.append("\t".join(cells))
        elif getattr(shape, "has_text_frame", False) and shape.has_text_frame and shape.shape_id != skip_id:
            text = shape.text_frame.text.strip()
            if text:
                lines.append(text)
    return images


def _extract(source: SourceFile, report: ParseReport, settings: Settings | None = None) -> list[ParsedBlock]:
    prs = pptx.Presentation(str(source.path))
    blocks: list[ParsedBlock] = []
    images = 0
    with OOXMLImages(source.path, settings) as collector:
        for slide in prs.slides:
            lines: list[str] = []
            title = slide.shapes.title
            skip_id = None
            if title is not None:
                skip_id = title.shape_id
                if title.text_frame.text.strip():
                    lines.append(title.text_frame.text.strip())
            images += _shape_lines(slide.shapes, skip_id, lines)
            if slide.has_notes_slide:
                notes = slide.notes_slide.notes_text_frame
                if notes is not None and notes.text.strip():
                    lines.append(notes.text.strip())
            assets = collector.for_element(slide._element, str(slide.part.partname))
            if lines or assets:
                blocks.append(ParsedBlock("\n".join(lines), "slide", assets=assets))
        if images and not collector.enabled:
            report.images_skipped += images
            report.add_note(f"{images} embedded images were skipped")
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
