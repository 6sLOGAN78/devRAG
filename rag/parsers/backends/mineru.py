"""MinerU 2.x/3.x JSON and 4.1 wrapper ZIP dialects."""

from __future__ import annotations

import hashlib
import io
import json
import math
import zipfile
from typing import Any

import httpx

from rag.parsers.backend_registry import BackendEndpoint, BackendUnavailable, page_box, request_attachment, request_json
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


def _structured_content(attachment: bytes) -> dict[str, Any]:
    """Read only the one structured result; never extract provider archive paths."""
    try:
        with zipfile.ZipFile(io.BytesIO(attachment)) as archive:
            entries = archive.infolist()
            if not 1 <= len(entries) <= 1000 or sum(entry.file_size for entry in entries) > 64 * 1024 * 1024:
                raise BackendUnavailable()
            names = [entry.filename for entry in entries]
            if names.count("structured_content.json") != 1:
                raise BackendUnavailable()
            for entry in entries:
                name = entry.filename
                if (not name or name.startswith("/") or "\\" in name or ":" in name
                        or any(part in {"", ".", ".."} for part in name.rstrip("/").split("/"))
                        or (name not in {"structured_content.json", "middle_json.json", "markdown.md", "images/"}
                            and not name.startswith("images/"))
                        or (entry.external_attr >> 16) & 0o170000 == 0o120000
                        or entry.file_size > 16 * 1024 * 1024):
                    raise BackendUnavailable()
            with archive.open("structured_content.json") as source:
                encoded = source.read(16 * 1024 * 1024 + 1)
            if len(encoded) > 16 * 1024 * 1024:
                raise BackendUnavailable()

        def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            values = dict(pairs)
            if len(values) != len(pairs):
                raise ValueError("duplicate provider JSON key")
            return values

        payload = json.loads(encoded, object_pairs_hook=unique_pairs)
        if not isinstance(payload, dict):
            raise BackendUnavailable()
        return payload
    except (OSError, ValueError, KeyError, RuntimeError, zipfile.BadZipFile, RecursionError):
        raise BackendUnavailable() from None


def normalize_v4(payload: dict[str, Any], page_sizes: dict[int, tuple[float, float]], selected: set[int], version: str) -> list[ParsedBlock]:
    """MinerU 4.1 structured content uses one-based source pages and 0..1 boxes."""
    try:
        if payload["metadata"]["producer"]["version"] != version or payload["extensions"]["mineru"]["tier"] != "basic":
            raise BackendUnavailable()
        pages = payload["pages"]
        if not isinstance(pages, list) or len(pages) > len(page_sizes):
            raise BackendUnavailable()
        blocks: list[ParsedBlock] = []
        seen_pages: set[int] = set()
        for page_data in pages:
            index = page_data["page_idx"]
            if type(index) is not int or index + 1 not in page_sizes or index in seen_pages:
                raise BackendUnavailable()
            seen_pages.add(index)
            page = index + 1
            if page not in selected:
                continue
            items = page_data["blocks"]
            if not isinstance(items, list) or len(items) > 100000:
                raise BackendUnavailable()
            for item in items:
                category = item["type"]
                if category in {"image", "chart"}:
                    continue
                if category not in {"doc_title", "paragraph_title", "text", "table", "equation", "code", "list", "header", "footer", "page_number", "page_footnote", "aside_text", "ref_text"}:
                    raise BackendUnavailable()
                content = item["content"]
                if not isinstance(content, str) or len(content.encode()) > 4 * 1024 * 1024:
                    raise BackendUnavailable()
                kind = "heading" if category in {"doc_title", "paragraph_title"} else "table" if category == "table" else "code" if category == "code" else "list" if category == "list" else "text"
                layout = "Title" if kind == "heading" else "Table" if kind == "table" else "Header" if category == "header" else "Footer" if category == "footer" else "Text"
                boxes = ()
                raw = item.get("bbox")
                if raw is not None:
                    if (not isinstance(raw, list) or len(raw) != 4
                            or any(type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1 for value in raw)):
                        raise BackendUnavailable()
                    width, height = page_sizes[page]
                    boxes = (page_box(page, (raw[0] * width, raw[1] * height, raw[2] * width, raw[3] * height), page_sizes),)
                blocks.append(ParsedBlock(content, kind, boxes, {page: page_sizes[page]}, layout_label=layout))
        return blocks
    except (KeyError, IndexError, TypeError, ValueError, RecursionError):
        raise BackendUnavailable() from None


def parse(content: bytes, endpoint: BackendEndpoint, page_sizes: dict[int, tuple[float, float]], selected: set[int], *, transport: httpx.BaseTransport | None = None) -> list[ParsedBlock]:
    if endpoint.version == "4.1.6":
        if not selected:
            raise BackendUnavailable()
        first, last = min(selected), max(selected)
        page_range = str(first) if first == last else f"{first}-{last}"
        request_id = hashlib.sha256(content + b"\0" + endpoint.version.encode() + b"\0" + page_range.encode()).hexdigest()
        attachment = request_attachment(endpoint, "/v1/file_parse", content,
                                        {"tier": "basic", "output_formats": "default", "page_range": page_range,
                                         "wait_timeout": "45", "request_id": request_id}, transport=transport)
        return normalize_v4(_structured_content(attachment), page_sizes, selected, endpoint.version)
    payload = request_json(endpoint, "/file_parse", content,
                           {"return_content_list": "true", "return_md": "false", "return_images": "false",
                            "response_format_zip": "false", "start_page_id": "0", "end_page_id": str(len(page_sizes) - 1)},
                           transport=transport)
    if payload.get("version") != endpoint.version:
        raise BackendUnavailable()
    return normalize(payload, page_sizes, selected)
