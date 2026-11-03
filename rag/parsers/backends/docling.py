"""Docling Serve JSON dialect: body references and provenance in PDF page units."""

from __future__ import annotations

from typing import Any

import httpx

from rag.parsers.backend_registry import BackendEndpoint, BackendUnavailable, page_box, request_json
from rag.parsers.types import ParsedBlock


def normalize(payload: dict[str, Any], page_sizes: dict[int, tuple[float, float]], selected: set[int]) -> list[ParsedBlock]:
    try:
        if payload["status"] != "success":
            raise BackendUnavailable()
        doc = payload["document"]["json_content"]
        if not isinstance(doc, dict) or not isinstance(doc["body"]["children"], list):
            raise BackendUnavailable()
        blocks: list[ParsedBlock] = []
        visited: set[str] = set()

        def visit(ref: str) -> None:
            if ref in visited or not ref.startswith("#/"):
                raise BackendUnavailable()
            visited.add(ref)
            parts = ref[2:].split("/")
            if len(parts) != 2 or parts[0] not in {"texts", "tables", "pictures", "groups"} or not parts[1].isdigit():
                raise BackendUnavailable()
            family, index = parts[0], int(parts[1])
            item = doc[family][index]
            if not isinstance(item, dict):
                raise BackendUnavailable()
            if family == "groups":
                for child in item["children"]:
                    visit(child["$ref"])
                return
            if family == "pictures":
                return  # Image references are never fetched or passed through.
            text = item.get("text", "")
            if family == "tables" and not text:
                data = item.get("data")
                if not isinstance(data, dict):
                    raise BackendUnavailable()
                cells = data.get("table_cells", [])
                text = "\n".join(cell["text"] for cell in cells)
            if not isinstance(text, str) or len(text) > 4 * 1024 * 1024:
                raise BackendUnavailable()
            label = item.get("label", "")
            kind = "table" if family == "tables" else "heading" if label in {"title", "section_header"} else "text"
            layout = "Table" if family == "tables" else "Title" if kind == "heading" else "Text"
            boxes = []
            for provenance in item.get("prov", []):
                page = provenance["page_no"]
                if type(page) is not int or page not in page_sizes:
                    raise BackendUnavailable()
                if page not in selected:
                    continue
                raw = provenance["bbox"]
                width, height = page_sizes[page]
                origin = raw["coord_origin"]
                if origin == "BOTTOMLEFT":
                    values = (raw["l"], height - raw["t"], raw["r"], height - raw["b"])
                elif origin == "TOPLEFT":
                    values = (raw["l"], raw["t"], raw["r"], raw["b"])
                else:
                    raise BackendUnavailable()
                boxes.append(page_box(page, values, page_sizes))
            if boxes:
                sizes = {box.page: page_sizes[box.page] for box in boxes}
                blocks.append(ParsedBlock(text, kind, tuple(boxes), sizes, layout_label=layout))
            elif text and not item.get("prov"):
                raise BackendUnavailable()

        for child in doc["body"]["children"]:
            visit(child["$ref"])
        return blocks
    except (KeyError, IndexError, TypeError, ValueError, RecursionError):
        raise BackendUnavailable() from None


def parse(content: bytes, endpoint: BackendEndpoint, page_sizes: dict[int, tuple[float, float]], selected: set[int], *, transport: httpx.BaseTransport | None = None) -> list[ParsedBlock]:
    payload = request_json(endpoint, "/v1/convert/file", content,
                           {"to_formats": "json", "image_export_mode": "placeholder"}, transport=transport)
    return normalize(payload, page_sizes, selected)
