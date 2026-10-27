"""Byte-only PDF operations; PDFium and image decoding stay inside DeepDoc."""

from __future__ import annotations

import io
import math
import tempfile
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, ValidationError

from deepdoc import pdf
from deepdoc.geometry import LABELS, apply_layout, iou
from deepdoc.model_runtime import NativeError
from rag.parsers.assets import MAX_ASSETS, encode_asset
from rag.parsers.errors import FileTooLarge, ParserError
from rag.parsers.types import PageBox, ParsedBlock, ParseReport


class PDFOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    start: StrictInt = Field(default=0, ge=0, le=1_000_000)
    end: StrictInt = Field(default=1_000_000, ge=0, le=1_000_000)
    page: StrictInt = Field(default=1, ge=1, le=1_000_000)
    zoom: int | float = Field(default=3, gt=0, le=3)
    thumbnail: StrictBool = False
    layout: StrictBool = False
    max_pages: StrictInt = Field(default=20000, ge=1, le=20000)
    max_text_bytes: StrictInt = Field(default=32 * 1024 * 1024, ge=1, le=100 * 1024 * 1024)


def _valid_native_text(blocks: list[ParsedBlock] | None) -> bool:
    text = "".join(block.text for block in blocks or [])
    if not text.strip():
        return False
    damaged = sum(char == "\ufffd" or (ord(char) < 32 and char not in "\n\r\t") for char in text)
    return damaged / len(text) <= 0.05


def _region_assets(image, regions, embedded, page, width, height):
    """Keep vector figure/table pixels with the actual detected source rectangle."""
    from deepdoc.images import normalize_image

    result = []
    produced_bytes = sum(len(a.content) for b in embedded for a in b.assets)
    for region in regions:
        label = LABELS[region.label_id]
        if label not in {"Figure", "Table"}:
            continue
        if any(iou(region.box, (b.boxes[0].x0, b.boxes[0].top, b.boxes[0].x1, b.boxes[0].bottom)) >= 0.8 for b in embedded):
            continue
        if len(result) + len(embedded) >= MAX_ASSETS:
            raise FileTooLarge()
        x0, top, x1, bottom = region.box
        x1, bottom = min(x1, width), min(bottom, height)
        if x0 >= x1 or top >= bottom:
            continue
        pixels = (math.floor(x0 * image.width / width), math.floor(top * image.height / height), math.ceil(x1 * image.width / width), math.ceil(bottom * image.height / height))
        cropped = image.crop(pixels)
        buffer = io.BytesIO()
        cropped.save(buffer, "PNG")
        asset = replace(normalize_image(buffer.getvalue()), page=page, kind="table" if label == "Table" else "image")
        produced_bytes += len(asset.content)
        if produced_bytes > 24 * 1024 * 1024:
            raise FileTooLarge()
        result.append(ParsedBlock("", boxes=(PageBox(page, x0, top, x1, bottom),), page_sizes={page: (width, height)}, layout_label=label, assets=(asset,)))
    return result


def _parse(path: Path, options: PDFOptions, ocr) -> dict[str, Any]:
    report = ParseReport()
    total = pdf.count_pages(path)
    if total > options.max_pages:
        raise FileTooLarge()
    start, end = min(total, options.start), min(total, options.end)
    end = max(start, end)
    report.pages_total = end - start
    blocks: list[ParsedBlock] = []
    document = pdf._open(path)
    produced = 0
    asset_count = asset_bytes = 0
    try:
        for index in range(start, end):
            page = document[index]
            try:
                page_blocks = pdf._page_blocks(page, index + 1, group_lines=not options.layout)
                width, height = page.get_size()
                asset_blocks = pdf.page_assets(page, index + 1)
            finally:
                page.close()
            image = None
            if not _valid_native_text(page_blocks):
                image = pdf.rasterize_page(path, index, zoom=3)
                buffer = io.BytesIO()
                image.save(buffer, "PNG")
                result = ocr.ocr(buffer.getvalue())
                page_blocks = []
                for span in result["spans"]:
                    x0, y0, x1, y1 = span["box"]
                    box = PageBox(index + 1, x0 * width / image.width, y0 * height / image.height, x1 * width / image.width, y1 * height / image.height)
                    page_blocks.append(ParsedBlock(span["text"], boxes=(box,), page_sizes={index + 1: (width, height)}))
                if not page_blocks:
                    report.pages_without_text += 1
            if options.layout:
                image = image if image is not None else pdf.rasterize_page(path, index, zoom=3)
                regions = ocr.layout(image, (width, height))
                page_blocks = apply_layout(page_blocks or [], regions)
                report.layout_backend = "deepdoc-onnx"
                report.layout_regions += len(regions)
                asset_blocks.extend(_region_assets(image, regions, asset_blocks, index + 1, width, height))
            asset_count += sum(len(b.assets) for b in asset_blocks)
            asset_bytes += sum(len(a.content) for b in asset_blocks for a in b.assets)
            if asset_count > MAX_ASSETS or asset_bytes > 24 * 1024 * 1024:
                raise FileTooLarge()
            for block in (page_blocks or []) + asset_blocks:
                produced += len(block.text.encode())
                if produced > options.max_text_bytes:
                    raise FileTooLarge()
                blocks.append(block)
    finally:
        document.close()
    wire = []
    for block in blocks:
        item = asdict(replace(block, assets=()))
        item["assets"] = [encode_asset(asset) for asset in block.assets]
        wire.append(item)
    return {"schema_version": 1, "blocks": wire, "report": asdict(report)}


def process(operation: str, content: bytes, raw_options: dict[str, Any], ocr) -> dict[str, Any] | bytes:
    try:
        options = PDFOptions.model_validate(raw_options)
        if options.end < options.start or not math.isfinite(options.zoom):
            raise NativeError("invalid_options")
    except ValidationError:
        raise NativeError("invalid_options") from None
    try:
        with tempfile.TemporaryDirectory(prefix="deepdoc-pdf-") as folder:
            path = Path(folder) / "source.pdf"
            path.write_bytes(content)
            if operation == "info":
                result = {"schema_version": 1, "pages_total": pdf.count_pages(path)}
                if options.thumbnail:
                    result["thumbnail"] = pdf.thumbnail_data_url(path)
                return result
            if operation == "parse":
                return _parse(path, options, ocr)
            if operation == "page-image":
                if options.page > pdf.count_pages(path):
                    raise NativeError("page_not_found", 404)
                image = pdf.rasterize_page(path, options.page - 1, options.zoom).convert("RGB")
                buffer = io.BytesIO()
                image.save(buffer, "JPEG", quality=80)
                return buffer.getvalue()
            raise NativeError("invalid_operation")
    except FileTooLarge:
        raise NativeError("file_too_large", 413) from None
    except (ParserError, pdf.pdfium.PdfiumError):
        raise NativeError("file_damaged") from None
