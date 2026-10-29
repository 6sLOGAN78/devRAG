"""Bounded authenticated PDF byte transport; imports no native parsing modules."""

from __future__ import annotations

import io
import json
import math
from pathlib import Path
from typing import Any

import httpx

from common.settings import DeepDocSettings
from rag.parsers.assets import InvalidAsset, ParsedAsset, decode_asset
from rag.parsers.errors import FileDamaged, FileTooLarge, NoReadableText, ParserError
from rag.parsers.tables import Table
from rag.parsers.types import BLOCK_KINDS, LAYOUT_LABELS, PageBox, ParsedBlock, ParseLimits, ParseReport, SourceFile


class NativeUnavailable(ParserError):
    code = "native_unavailable"
    message = "the native parsing service is not available"


class DeepDocClient:
    def __init__(self, settings: DeepDocSettings, *, transport: httpx.BaseTransport | None = None):
        self.settings, self.transport = settings, transport

    def _request(self, endpoint: str, path: Path | bytes, options: dict[str, Any] | None, *, binary: bool = False):
        if not self.settings.url or len(self.settings.api_token) < 24:
            raise NativeUnavailable()
        try:
            size = len(path) if isinstance(path, bytes) else path.stat().st_size
            if size > 100 * 1024 * 1024:
                raise FileTooLarge()
            stream = io.BytesIO(path) if isinstance(path, bytes) else path.open("rb")
            with (
                stream as source,
                httpx.Client(
                    base_url=self.settings.url,
                    timeout=self.settings.timeout_seconds,
                    transport=self.transport,
                    follow_redirects=False,
                    trust_env=False,
                ) as client,
            ):
                with client.stream(
                    "POST",
                    endpoint,
                    headers={"Authorization": f"Bearer {self.settings.api_token}"},
                    files={"file": ("source.bin", source, "application/octet-stream")},
                    data={} if options is None else {"options": json.dumps(options)},
                ) as response:
                    if response.status_code == 413:
                        raise FileTooLarge()
                    if response.status_code == 400:
                        if endpoint == "/v1/asr":
                            refusal = bytearray()
                            for part in response.iter_bytes():
                                refusal.extend(part)
                                if len(refusal) > 4096:
                                    raise NativeUnavailable()
                            refused = json.loads(refusal)
                            if not isinstance(refused, dict):
                                raise NativeUnavailable()
                            if refused.get("error") == "no_readable_text":
                                raise NoReadableText()
                        raise FileDamaged()
                    if response.status_code != 200:
                        raise NativeUnavailable()
                    result = bytearray()
                    for chunk in response.iter_bytes():
                        result.extend(chunk)
                        if len(result) > 32 * 1024 * 1024:
                            raise FileTooLarge()
                    if binary:
                        if not response.headers.get("content-type", "").startswith("image/jpeg") or not result.startswith(b"\xff\xd8"):
                            raise NativeUnavailable()
                        return bytes(result)
                    data = json.loads(result)
                    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
                        raise NativeUnavailable()
                    return data
        except (httpx.HTTPError, ValueError, RecursionError, OSError):
            raise NativeUnavailable() from None

    def document_info(self, path: Path, *, thumbnail: bool = False) -> dict[str, Any]:
        data = self._request("/v1/document/info", path, {"thumbnail": thumbnail})
        total = data.get("pages_total")
        if type(total) is not int or not 0 <= total <= 1_000_000:
            raise NativeUnavailable()
        if thumbnail:
            image = data.get("thumbnail")
            if not isinstance(image, str) or len(image) > 16384 or not image.startswith("data:image/jpeg;base64,"):
                raise NativeUnavailable()
        return data

    def ocr_image(self, content: bytes) -> dict:
        from deepdoc.ocr_result import validate_result
        from deepdoc.model_runtime import NativeError
        data = self._request("/v1/ocr", content, None)
        try:
            validate_result(data)
        except (NativeError,TypeError,KeyError):
            raise NativeUnavailable() from None
        return data

    def normalize_image(self, content: bytes) -> ParsedAsset:
        if len(content) > 16 * 1024 * 1024:
            raise FileTooLarge()
        data = self._request("/v1/images/normalize", content, None)
        try:
            return decode_asset(data["image"])
        except (KeyError, InvalidAsset):
            raise NativeUnavailable() from None

    def page_image(self, path: Path, page: int, zoom: float = 3) -> bytes:
        return self._request("/v1/page-image", path, {"page": page, "zoom": zoom}, binary=True)

    def parse(self, source: SourceFile, report: ParseReport, *, page_range: tuple[int, int] | None, limits: ParseLimits | None, parser_config: dict[str, Any] | None = None) -> list[ParsedBlock]:
        limit = limits or ParseLimits()
        layout = (parser_config or {}).get("layout_recognize", False)
        if type(layout) is not bool and layout != "deepdoc":
            raise NativeUnavailable()
        options = {"max_pages": limit.max_pages, "max_text_bytes": limit.max_text_bytes, "layout": layout is not False}
        if page_range is not None:
            options.update(start=page_range[0], end=page_range[1])
        data = self._request("/v1/parse", source.path, options)
        try:
            raw_blocks, raw_report = data["blocks"], data["report"]
            if not isinstance(raw_blocks, list) or len(raw_blocks) > 100000:
                raise ValueError
            total, missing = raw_report["pages_total"], raw_report["pages_without_text"]
            if type(total) is not int or type(missing) is not int or not 0 <= missing <= total <= limit.max_pages:
                raise ValueError
            backend, regions = raw_report.get("layout_backend"), raw_report.get("layout_regions", 0)
            if backend not in (None, "deepdoc-onnx") or type(regions) is not int or not 0 <= regions <= 300 * total:
                raise ValueError
            if options["layout"] and backend != "deepdoc-onnx" and total:
                raise ValueError
            blocks, size = [], 0
            for raw in raw_blocks:
                text, kind = raw["text"], raw["kind"]
                if not isinstance(text, str) or kind not in BLOCK_KINDS:
                    raise ValueError
                size += len(text.encode())
                if size > limit.max_text_bytes:
                    raise FileTooLarge()
                if not isinstance(raw["page_sizes"], dict):
                    raise ValueError
                sizes = {int(k): tuple(v) for k, v in raw["page_sizes"].items()}
                for page, dimensions in sizes.items():
                    if not 1 <= page <= 1_000_000 or len(dimensions) != 2:
                        raise ValueError
                    if any(type(x) not in (int, float) or not math.isfinite(x) or x <= 0 for x in dimensions):
                        raise ValueError
                boxes = []
                for box in raw["boxes"]:
                    page = box["page"]
                    if type(page) is not int or page not in sizes:
                        raise ValueError
                    if page_range is not None and not page_range[0] < page <= page_range[1]:
                        raise ValueError
                    x0, top, x1, bottom = (box[key] for key in ("x0", "top", "x1", "bottom"))
                    if any(type(x) not in (int, float) or not math.isfinite(x) for x in (x0, top, x1, bottom)):
                        raise ValueError
                    width, height = sizes[page]
                    if not -1 <= x0 < x1 <= width + 1 or not -1 <= top < bottom <= height + 1:
                        raise ValueError
                    boxes.append(PageBox(page, x0, top, x1, bottom))
                label = raw.get("layout_label")
                if label is not None and label not in LAYOUT_LABELS:
                    raise ValueError
                raw_assets = raw.get("assets", [])
                if not isinstance(raw_assets, list) or len(raw_assets) > 128:
                    raise ValueError
                assets = tuple(decode_asset(value) for value in raw_assets)
                table = Table.from_wire(raw["table"]) if raw.get("table") is not None else None
                if table is not None:
                    crops = [a for a in assets if a.kind == "table" and a.sha256 == table.asset_sha256]
                    if table.asset_id or len(crops) != 1 or len(boxes) != 1:
                        raise ValueError
                    crop, box = crops[0], boxes[0]
                    if crop.page != box.page or abs(crop.width - (box.x1 - box.x0) * 3) > 2 or abs(crop.height - (box.bottom - box.top) * 3) > 2:
                        raise ValueError
                blocks.append(ParsedBlock(text, kind, tuple(boxes), sizes, layout_label=label, assets=assets, table=table))
            report.pages_total, report.pages_without_text = total, missing
            report.layout_backend, report.layout_regions = backend, regions
            return blocks
        except (KeyError, TypeError, ValueError, OverflowError, InvalidAsset):
            raise NativeUnavailable() from None
