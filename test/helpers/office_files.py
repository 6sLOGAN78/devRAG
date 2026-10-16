"""Generated Office and HTML files for parser tests (plan 04-09). Built with the approved libraries plus zipfile."""
from __future__ import annotations

import io
import os
import zipfile
from collections.abc import Sequence
from pathlib import Path

import docx
import openpyxl
import pptx
from docx.shared import Inches
from pptx.util import Inches as PInches

_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360f8cfc00000030101009a6e37190000000049454e44ae426082"
)


def make_docx(
    paragraphs: Sequence[str] = (),
    headings: Sequence[str] = (),
    table: Sequence[Sequence[str]] | None = None,
    image: bool = False,
) -> bytes:
    doc = docx.Document()
    for heading in headings:
        doc.add_heading(heading, level=1)
    for text in paragraphs:
        doc.add_paragraph(text)
    if table:
        grid = doc.add_table(rows=len(table), cols=len(table[0]))
        for r, row in enumerate(table):
            for c, cell in enumerate(row):
                grid.cell(r, c).text = cell
    if image:
        doc.add_picture(io.BytesIO(_PNG), width=Inches(1))
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def make_xlsx(sheets: dict[str, Sequence[Sequence[object]]]) -> bytes:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for row in rows:
            ws.append(list(row))
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def make_pptx(slides: Sequence[dict]) -> bytes:
    """Each slide dict: title, body, notes, table (rows), image (bool)."""
    prs = pptx.Presentation()
    for spec in slides:
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = spec.get("title", "")
        slide.placeholders[1].text = spec.get("body", "")
        if spec.get("notes"):
            slide.notes_slide.notes_text_frame.text = spec["notes"]
        rows = spec.get("table")
        if rows:
            shape = slide.shapes.add_table(len(rows), len(rows[0]), PInches(1), PInches(4), PInches(6), PInches(1))
            for r, row in enumerate(rows):
                for c, cell in enumerate(row):
                    shape.table.cell(r, c).text = cell
        if spec.get("image"):
            slide.shapes.add_picture(io.BytesIO(_PNG), PInches(1), PInches(1), PInches(1))
    out = io.BytesIO()
    prs.save(out)
    return out.getvalue()


def make_html(markup: str, encoding: str = "utf-8") -> bytes:
    return markup.encode(encoding)


def make_zip_bomb(path: Path, member_bytes: int) -> Path:
    """A zip holding one member of zeros; member_bytes of zeros deflate to a few KiB."""
    piece = b"\0" * 2**20
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf, zf.open("word/bomb.bin", "w") as member:
        left = member_bytes
        while left > 0:
            member.write(piece[: min(left, len(piece))])
            left -= len(piece)
    return path


def _rezip(data: bytes, replace: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            dst.writestr(info.filename, replace.get(info.filename, src.read(info.filename)))
    return out.getvalue()


def make_entity_docx() -> bytes:
    hostile = (
        b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/hostname">]>'
        b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        b"<w:body><w:p><w:r><w:t>&e;</w:t></w:r></w:p></w:body></w:document>"
    )
    return _rezip(make_docx(["x"]), {"word/document.xml": hostile})


def poison_docx() -> bytes:
    return b"PK\x03\x04" + os.urandom(200)
