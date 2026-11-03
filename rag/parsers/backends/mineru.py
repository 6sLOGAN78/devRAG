"""MinerU legacy /file_parse content-list dialect with 0..1000 bboxes."""

from __future__ import annotations

import json
from typing import Any

import httpx

from rag.parsers.backend_registry import BackendEndpoint, BackendUnavailable, page_box, request_json
from rag.parsers.types import ParsedBlock


def normalize(payload: dict[str, Any], page_sizes: dict[int, tuple[float, float]], selected: set[int]) -> list[ParsedBlock]:
    try:
        if payload.get("status") not in {None, "success", "completed"}:
            raise BackendUnavailable()
        if not isinstance(payload.get("version"), str) or not payload["version"].startswith(("2.", "3.")):
            raise BackendUnavailable()
        # A single file is submitted. A response containing more than one result is ambiguous.
        results = payload["results"]
        if not isinstance(results, dict) or len(results) != 1:
            raise BackendUnavailable()
        only = next(iter(results.values()))
        if not isinstance(only, dict):
            raise BackendUnavailable()
        if only.get("error"):
            raise BackendUnavailable()
        encoded = only["content_list"]
        if not isinstance(encoded, str) or len(encoded.encode()) > 16 * 1024 * 1024:
            raise BackendUnavailable()
        content_list = json.loads(encoded)
        if not isinstance(content_list, list) or len(content_list) > 100000:
            raise BackendUnavailable()
        blocks: list[ParsedBlock] = []
        for item in content_list:
            page = item["page_idx"] + 1
            if type(item["page_idx"]) is not int or page not in page_sizes:
                raise BackendUnavailable()
            if page not in selected:
                continue
            text = item.get("text", "")
            if item.get("type") == "table" and not text:
                text = item.get("table_body", "")
            if not isinstance(text, str) or len(text) > 4 * 1024 * 1024:
                raise BackendUnavailable()
            category = item.get("type")
            if category in {"image", "chart"}:
                continue  # No image bytes are requested or trusted from this dialect.
            if category not in {"text", "title", "table", "equation", "code", "list", "header", "footer", "page_number"}:
                raise BackendUnavailable()
            level = item.get("text_level", 0)
            if type(level) is not int or not 0 <= level <= 6:
                raise BackendUnavailable()
            kind = "table" if category == "table" else "heading" if category == "title" or level else category if category in {"code", "list"} else "text"
            layout = {
                "table": "Table", "heading": "Title", "header": "Header", "footer": "Footer", "equation": "Equation",
            }.get(kind if kind in {"table", "heading"} else category, "Text")
            boxes = ()
            if item.get("bbox") is not None:
                raw = item["bbox"]
                if not isinstance(raw, list) or len(raw) != 4 or any(type(v) not in (int, float) or not 0 <= v <= 1000 for v in raw):
                    raise BackendUnavailable()
                width, height = page_sizes[page]
                boxes = (page_box(page, (raw[0] * width / 1000, raw[1] * height / 1000,
                                         raw[2] * width / 1000, raw[3] * height / 1000), page_sizes),)
            blocks.append(ParsedBlock(text, kind, boxes, {page: page_sizes[page]}, layout_label=layout))
        return blocks
    except (KeyError, IndexError, TypeError, ValueError, RecursionError):
        raise BackendUnavailable() from None


def parse(content: bytes, endpoint: BackendEndpoint, page_sizes: dict[int, tuple[float, float]], selected: set[int], *, transport: httpx.BaseTransport | None = None) -> list[ParsedBlock]:
    payload = request_json(endpoint, "/file_parse", content,
                           {"return_content_list": "true", "return_md": "false", "return_images": "false",
                            "response_format_zip": "false", "start_page_id": "0", "end_page_id": str(len(page_sizes) - 1)},
                           transport=transport)
    if payload.get("version") != endpoint.version:
        raise BackendUnavailable()
    return normalize(payload, page_sizes, selected)
