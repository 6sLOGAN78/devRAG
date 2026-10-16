"""PDF text, places, page images and thumbnails on pypdfium2 only (PARSE-02, PARSE-03, DOC-20, D-14, R-161).

pdfium is not thread safe, so every call runs under one process-wide lock and every page, text page and bitmap is closed in
``finally`` (RESEARCH Pitfall 8). Boxes are PDF points with the origin at the top left of the displayed (cropped, rotated) page.
"""

from __future__ import annotations

import base64
import io
import threading
from collections.abc import Iterator
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image
from pypdfium2 import PdfiumError

from rag.parsers.errors import FileDamaged, FileTooLarge
from rag.parsers.types import PageBox, ParsedBlock, ParseLimits, ParseReport, SourceFile

PDFIUM_LOCK = threading.RLock()
MAX_PAGES = 1_000_000
GAP_RATIO = 0.8


def _open(path: Path) -> pdfium.PdfDocument:
    try:
        return pdfium.PdfDocument(str(path))
    except (PdfiumError, OSError, ValueError):
        raise FileDamaged() from None


def count_pages(path: Path) -> int:
    with PDFIUM_LOCK:
        pdf = _open(path)
        try:
            total = len(pdf)
        except PdfiumError:
            raise FileDamaged() from None
        finally:
            pdf.close()
    if total > MAX_PAGES:
        raise FileTooLarge()
    return total


def _to_display(rect: tuple[float, float, float, float], crop: tuple[float, float, float, float], rotation: int) -> tuple[float, float, float, float]:
    """Map a pdfium user-space rect (left, bottom, right, top) to (x0, top, x1, bottom) in the displayed page."""
    left, bottom, right, top = rect
    cx0, cy0, cx1, cy1 = crop
    width, height = cx1 - cx0, cy1 - cy0
    # top-left frame of the unrotated crop box
    pts = [(x - cx0, height - (y - cy0)) for x in (left, right) for y in (bottom, top)]
    out: list[tuple[float, float]] = []
    for u, v in pts:
        if rotation == 90:
            out.append((height - v, u))
        elif rotation == 180:
            out.append((width - u, height - v))
        elif rotation == 270:
            out.append((v, width - u))
        else:
            out.append((u, v))
    xs = [p[0] for p in out]
    ys = [p[1] for p in out]
    return min(xs), min(ys), max(xs), max(ys)


def _page_blocks(page: pdfium.PdfPage, number: int) -> list[ParsedBlock] | None:
    """Blocks of one page, or None when the page has no text layer."""
    text_page = page.get_textpage()
    try:
        if not text_page.get_text_range().strip():
            return None
        crop = page.get_cropbox()
        rotation = page.get_rotation() % 360
        size = page.get_size()
        lines: list[tuple[str, tuple[float, float, float, float]]] = []
        for k in range(text_page.count_rects()):
            rect = text_page.get_rect(k)
            text = text_page.get_text_bounded(*rect).strip()
            if text:
                lines.append((text, _to_display(rect, crop, rotation)))
        lines.sort(key=lambda item: (round(item[1][1], 1), item[1][0]))
    finally:
        text_page.close()
    blocks: list[ParsedBlock] = []
    group: list[tuple[str, tuple[float, float, float, float]]] = []

    def flush() -> None:
        if not group:
            return
        box = PageBox(number, min(b[0] for _, b in group), min(b[1] for _, b in group), max(b[2] for _, b in group), max(b[3] for _, b in group))
        blocks.append(ParsedBlock(text="\n".join(t for t, _ in group), boxes=(box,), page_sizes={number: size}))
        group.clear()

    for text, box in lines:
        if group:
            prev = group[-1][1]
            height = max(prev[3] - prev[1], 1e-6)
            if box[1] - prev[3] >= GAP_RATIO * height:
                flush()
        group.append((text, box))
    flush()
    return blocks


def parse(source: SourceFile, report: ParseReport, *, page_range: tuple[int, int] | None = None, limits: ParseLimits | None = None) -> Iterator[ParsedBlock]:
    """Yield text blocks of the page range (0-based, end exclusive, clamped). Errors are raised when the call is made."""
    total = count_pages(source.path)
    start, end = (0, total) if page_range is None else (max(0, page_range[0]), min(total, page_range[1]))
    end = max(start, end)
    report.pages_total = end - start
    return _iter_pages(source.path, start, end, report)


def _iter_pages(path: Path, start: int, end: int, report: ParseReport) -> Iterator[ParsedBlock]:
    for index in range(start, end):
        with PDFIUM_LOCK:
            pdf = _open(path)
            try:
                page = pdf[index]
                try:
                    blocks = _page_blocks(page, index + 1)
                finally:
                    page.close()
            except PdfiumError:
                raise FileDamaged() from None
            finally:
                pdf.close()
        if blocks is None:
            report.pages_without_text += 1
            continue
        yield from blocks


def rasterize_page(path: Path, index: int, zoom: float = 3.0) -> Image.Image:
    with PDFIUM_LOCK:
        pdf = _open(path)
        try:
            page = pdf[index]
            try:
                bitmap = page.render(scale=zoom)
                try:
                    return bitmap.to_pil().copy()
                finally:
                    bitmap.close()
            finally:
                page.close()
        except (PdfiumError, IndexError):
            raise FileDamaged() from None
        finally:
            pdf.close()


def thumbnail_data_url(path: Path, max_chars: int = 16384) -> str:
    image = rasterize_page(path, 0, 0.5).convert("RGB")
    height = max(1, round(image.height * 160 / image.width))
    image = image.resize((160, height))
    prefix = "data:image/jpeg;base64,"
    url = ""
    for quality in (70, 60, 50, 40, 30, 20):
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=quality)
        url = prefix + base64.b64encode(buffer.getvalue()).decode("ascii")
        if len(url) <= max_chars:
            return url
    return url
