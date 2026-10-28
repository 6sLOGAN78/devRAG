"""Native PDF text, places, page images and thumbnails inside DeepDoc (PARSE-02, PARSE-03, DOC-20, D-14, R-161).

pdfium is not thread safe, so every call runs under one process-wide lock and every page, text page and bitmap is closed in
``finally`` (RESEARCH Pitfall 8). Boxes are PDF points with the origin at the top left of the displayed (cropped, rotated) page.
"""

from __future__ import annotations

import base64
import io
import math
import threading
from collections.abc import Iterator
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image
from pypdfium2 import PdfiumError

from rag.parsers.errors import FileDamaged, FileTooLarge
from rag.parsers.types import PageBox, ParsedBlock, ParseLimits, ParseReport, SourceFile

PDFIUM_LOCK = threading.RLock()
MAX_PAGES = 1_000_000  # hard ceiling for count_pages(); parse() applies the tighter ParseLimits.max_pages
MAX_PIXELS = 40_000_000  # render budget: zoom 3 on A4 is 4.5 MP, on A0 about 36 MP
MAX_SIDE = 12_000  # px per side
MAX_PAGE_POINTS = 14_400  # 200 in, the practical PDF page limit; larger pages are refused
THUMB_TARGET_WIDTH = 320  # px rendered before the 160 px downscale
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


def _page_blocks(page: pdfium.PdfPage, number: int, *, group_lines: bool = True) -> list[ParsedBlock] | None:
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
    if not group_lines:
        return [ParsedBlock(text, boxes=(PageBox(number, *box),), page_sizes={number: size}) for text, box in lines]
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
    limits = limits or ParseLimits()
    total = count_pages(source.path)
    if total > limits.max_pages:
        raise FileTooLarge()
    start, end = (0, total) if page_range is None else (max(0, page_range[0]), min(total, page_range[1]))
    end = max(start, end)
    report.pages_total = end - start
    return _iter_pages(source.path, start, end, report, limits.max_text_bytes)


def _iter_pages(path: Path, start: int, end: int, report: ParseReport, max_text_bytes: int) -> Iterator[ParsedBlock]:
    """Open the document once for the range; every pdfium call (including close) runs under PDFIUM_LOCK."""
    with PDFIUM_LOCK:
        pdf = _open(path)
    produced = 0
    try:
        for index in range(start, end):
            with PDFIUM_LOCK:
                try:
                    page = pdf[index]
                    try:
                        blocks = _page_blocks(page, index + 1)
                    finally:
                        page.close()
                except PdfiumError:
                    raise FileDamaged() from None
            if blocks is None:
                report.pages_without_text += 1
                continue
            for block in blocks:
                produced += len(block.text.encode("utf-8"))
                if produced > max_text_bytes:
                    raise FileTooLarge()
                yield block
    finally:
        with PDFIUM_LOCK:
            pdf.close()


def _render_scale(page: pdfium.PdfPage, zoom: float) -> float:
    """Scale not above ``zoom`` that keeps the bitmap within MAX_PIXELS and MAX_SIDE; absurd page sizes raise FileTooLarge."""
    width, height = page.get_size()
    if not (math.isfinite(width) and math.isfinite(height)) or width <= 0 or height <= 0:
        raise FileDamaged()
    if max(width, height) > MAX_PAGE_POINTS:
        raise FileTooLarge()
    return min(zoom, math.sqrt(MAX_PIXELS / (width * height)), MAX_SIDE / max(width, height))


def rasterize_page(path: Path, index: int, zoom: float = 3.0, *, target_width: int | None = None) -> Image.Image:
    """Render a page at ``zoom`` (or at ``target_width`` px when given), clamped to the pixel budget."""
    with PDFIUM_LOCK:
        pdf = _open(path)
        try:
            page = pdf[index]
            try:
                if target_width is not None:
                    zoom = target_width / max(page.get_size()[0], 1.0)
                bitmap = page.render(scale=_render_scale(page, zoom))
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
    image = rasterize_page(path, 0, target_width=THUMB_TARGET_WIDTH).convert("RGB")
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


def page_assets(page, number: int) -> list[ParsedBlock]:
    """Extract embedded pixels under the native pixel budget and canonical page geometry."""
    from dataclasses import replace

    from deepdoc.images import normalize_image
    from rag.parsers.assets import MAX_ASSETS

    blocks = []
    produced_bytes = 0
    for obj in page.get_objects(filter=[pdfium.raw.FPDF_PAGEOBJ_IMAGE], max_depth=15):
        try:
            if len(blocks) >= MAX_ASSETS:
                raise FileTooLarge()
            metadata = obj.get_metadata()
            if not 0 < metadata.width * metadata.height <= MAX_PIXELS:
                raise FileTooLarge()
            bitmap = obj.get_bitmap(render=False)
            try:
                image = bitmap.to_pil()
                buffer = io.BytesIO()
                image.save(buffer, "PNG")
            finally:
                bitmap.close()
            asset = replace(normalize_image(buffer.getvalue()), page=number)
            produced_bytes += len(asset.content)
            if produced_bytes > 24 * 1024 * 1024:
                raise FileTooLarge()
            box = _to_display(obj.get_bounds(), page.get_cropbox(), page.get_rotation() % 360)
            width, height = page.get_size()
            box = (max(0, box[0]), max(0, box[1]), min(width, box[2]), min(height, box[3]))
            if box[0] < box[2] and box[1] < box[3]:
                blocks.append(ParsedBlock("", boxes=(PageBox(number, *box),), page_sizes={number: (width, height)}, layout_label="Figure", assets=(asset,)))
        finally:
            obj.close()
    return blocks


def page_words(page) -> list:
    """Native word rectangles; do not assign a whole fused line to one table cell."""
    from deepdoc.tables import TextToken

    text_page = page.get_textpage()
    words = []
    chars = []
    boxes = []
    crop, rotation = page.get_cropbox(), page.get_rotation() % 360

    def flush():
        if chars and boxes:
            words.append(TextToken("".join(chars), (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))))
        chars.clear()
        boxes.clear()

    try:
        if text_page.count_chars() > 1_000_000:
            raise FileTooLarge()
        for index in range(text_page.count_chars()):
            char = text_page.get_text_range(index=index, count=1)
            if not char or char.isspace():
                flush()
                continue
            box = _to_display(text_page.get_charbox(index), crop, rotation)
            if box[0] >= box[2] or box[1] >= box[3]:
                continue
            if boxes and (
                abs((box[1] + box[3] - boxes[-1][1] - boxes[-1][3]) / 2) > max(3, max(box[3] - box[1], boxes[-1][3] - boxes[-1][1]) * 0.8) or box[0] - boxes[-1][2] > max(3, max(box[2] - box[0], boxes[-1][2] - boxes[-1][0]) * 1.5)
            ):
                flush()
            chars.append(char)
            boxes.append(box)
            if len(words) > 20000:
                raise FileTooLarge()
        flush()
    finally:
        text_page.close()
    return words
