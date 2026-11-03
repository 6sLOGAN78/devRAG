"""Operator-only optional PDF services and bounded response normalization."""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from rag.parsers.types import PageBox, ParsedBlock


class BackendUnavailable(Exception):
    """A selected provider is absent or did not return its declared dialect."""


@dataclass(frozen=True)
class BackendEndpoint:
    url: str
    version: str
    token: str = ""

    def __post_init__(self) -> None:
        try:
            parsed = urlsplit(self.url)
            valid = (parsed.scheme in {"http", "https"} and bool(parsed.hostname) and parsed.port != 0
                     and not parsed.username and not parsed.password and not parsed.query
                     and not parsed.fragment and parsed.path in {"", "/"})
        except ValueError:
            valid = False
        if not valid or not self.version or len(self.version) > 64 or any(c.isspace() for c in self.version):
            raise ValueError("invalid operator backend endpoint")


def request_json(endpoint: BackendEndpoint, path: str, content: bytes, fields: dict[str, str], *, transport: httpx.BaseTransport | None = None) -> dict[str, Any]:
    """Send one PDF, never follow redirects, and cap the complete JSON response."""
    if not content.startswith(b"%PDF-") or len(content) > 100 * 1024 * 1024:
        raise BackendUnavailable()
    headers = {"Accept": "application/json"}
    if endpoint.token:
        headers["Authorization"] = f"Bearer {endpoint.token}"
    try:
        with httpx.Client(base_url=endpoint.url, timeout=50, transport=transport, follow_redirects=False, trust_env=False) as client:
            with client.stream("POST", path, headers=headers, files={"files": ("source.pdf", content, "application/pdf")}, data=fields) as response:
                if response.status_code != 200 or "application/json" not in response.headers.get("content-type", ""):
                    raise BackendUnavailable()
                payload = bytearray()
                for chunk in response.iter_bytes():
                    payload.extend(chunk)
                    if len(payload) > 32 * 1024 * 1024:
                        raise BackendUnavailable()
        def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            values = dict(pairs)
            if len(values) != len(pairs):
                raise ValueError("duplicate provider JSON key")
            return values

        result = json.loads(payload, object_pairs_hook=unique_pairs)
        if not isinstance(result, dict):
            raise BackendUnavailable()
        return result
    except (httpx.HTTPError, OSError, ValueError, RecursionError):
        raise BackendUnavailable() from None


def page_box(page: int, values: tuple[float, float, float, float], page_sizes: dict[int, tuple[float, float]]) -> PageBox:
    if type(page) is not int or page not in page_sizes:
        raise BackendUnavailable()
    width, height = page_sizes[page]
    x0, top, x1, bottom = values
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        raise BackendUnavailable()
    if not 0 <= x0 < x1 <= width or not 0 <= top < bottom <= height:
        raise BackendUnavailable()
    return PageBox(page, x0, top, x1, bottom)


def wire_result(name: str, blocks: list[ParsedBlock], page_sizes: dict[int, tuple[float, float]], max_text_bytes: int) -> dict[str, Any]:
    if not blocks or len(blocks) > 100000 or sum(len(block.text.encode()) for block in blocks) > max_text_bytes:
        raise BackendUnavailable()
    pages_with_text = {box.page for block in blocks if block.text.strip() for box in block.boxes}
    wire = []
    for block in blocks:
        item = asdict(replace(block, assets=(), table=None))
        item["assets"], item["table"] = [], None
        wire.append(item)
    return {"schema_version": 1, "blocks": wire,
            "report": {"pages_total": len(page_sizes), "pages_without_text": len(page_sizes) - len(pages_with_text),
                       "layout_backend": name, "layout_regions": len([block for block in blocks if block.boxes])}}


def configured_endpoint(name: str) -> BackendEndpoint:
    """Read only process-level operator settings, never document-submitted options."""
    if name not in {"docling", "mineru"}:
        raise BackendUnavailable()
    prefix = f"PDF_BACKEND_{name.upper()}"
    url = os.environ.get(f"{prefix}_URL", "")
    version = os.environ.get(f"{prefix}_VERSION", "")
    if not url or not version:
        raise BackendUnavailable()
    # MinerU 4 uses a different task/result schema. The V1 content-list dialect is only 2.x/3.x.
    if name == "mineru" and not version.startswith(("2.", "3.")):
        raise BackendUnavailable()
    try:
        return BackendEndpoint(url, version, os.environ.get(f"{prefix}_TOKEN", ""))
    except ValueError:
        raise BackendUnavailable() from None


def run_selected(name: str, content: bytes, raw_options: dict[str, Any]) -> dict[str, Any]:
    """Called by DeepDoc's single executor; inspect the original PDF for canonical page dimensions."""
    from pydantic import ValidationError

    from deepdoc import pdf
    from deepdoc.model_runtime import NativeError
    from deepdoc.pdf_service import PDFOptions
    from rag.parsers.errors import FileDamaged, FileTooLarge

    if name not in {"docling", "mineru"} or raw_options.get("backend") != name:
        raise NativeError("invalid_options")
    try:
        options = PDFOptions.model_validate({key: value for key, value in raw_options.items() if key != "backend"})
        if not options.layout or options.end < options.start:
            raise NativeError("invalid_options")
    except ValidationError:
        raise NativeError("invalid_options") from None
    try:
        endpoint = configured_endpoint(name)
    except BackendUnavailable:
        raise NativeError("backend_unavailable", 503) from None
    try:
        with tempfile.TemporaryDirectory(prefix="deepdoc-external-") as folder:
            path = Path(folder) / "source.pdf"
            path.write_bytes(content)
            with pdf.PDFIUM_LOCK:
                document = pdf._open(path)
                try:
                    total = len(document)
                    if total == 0 or total > options.max_pages:
                        raise BackendUnavailable()
                    page_sizes = {}
                    for index in range(total):
                        page = document[index]
                        try:
                            size = page.get_size()
                            if any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0 or value > 14400 for value in size):
                                raise BackendUnavailable()
                            page_sizes[index + 1] = size
                        finally:
                            page.close()
                finally:
                    document.close()
            selected = set(range(max(0, options.start) + 1, min(total, options.end) + 1))
            if not selected:
                raise BackendUnavailable()
            if name == "docling":
                from rag.parsers.backends.docling import parse
            else:
                from rag.parsers.backends.mineru import parse
            blocks = parse(content, endpoint, page_sizes, selected)
            return wire_result(name, blocks, {page: page_sizes[page] for page in selected}, options.max_text_bytes)
    except FileTooLarge:
        raise NativeError("file_too_large", 413) from None
    except FileDamaged:
        raise NativeError("file_damaged", 400) from None
    except (BackendUnavailable, OSError, pdf.pdfium.PdfiumError):
        raise NativeError("backend_failure", 502) from None
