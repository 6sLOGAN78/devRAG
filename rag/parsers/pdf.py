"""PDF boundary: native implementation is lazy and remote selection never falls back."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from common.settings import Settings
from rag.parsers.types import ParsedBlock, ParseLimits, ParseReport, SourceFile


def _native():
    from deepdoc import pdf

    return pdf


def __getattr__(name: str) -> Any:
    # Backward-compatible constants/geometry for direct parser tests and local tools.
    if name.startswith("__"):
        raise AttributeError(name)
    return getattr(_native(), name)


def count_pages(path: Path, *, settings: Settings | None = None) -> int:
    if settings is not None and settings.deepdoc.url:
        from rag.parsers.deepdoc_client import DeepDocClient

        return DeepDocClient(settings.deepdoc).document_info(path)["pages_total"]
    return _native().count_pages(path)


def parse(source: SourceFile, report: ParseReport, *, page_range: tuple[int, int] | None = None,
          limits: ParseLimits | None = None, settings: Settings | None = None,
          parser_config: dict[str, Any] | None = None) -> Iterator[ParsedBlock]:
    if settings is not None and settings.deepdoc.url:
        from rag.parsers.deepdoc_client import DeepDocClient

        return iter(DeepDocClient(settings.deepdoc).parse(source, report, page_range=page_range, limits=limits))
    return _native().parse(source, report, page_range=page_range, limits=limits)


def rasterize_page(path: Path, index: int, zoom: float = 3.0, *, target_width: int | None = None):
    """Legacy/local tools only; remote product previews use raw JPEG through DeepDocClient."""
    return _native().rasterize_page(path, index, zoom, target_width=target_width)


def thumbnail_data_url(path: Path, max_chars: int = 16384, *, settings: Settings | None = None) -> str:
    if settings is not None and settings.deepdoc.url:
        from rag.parsers.deepdoc_client import DeepDocClient

        return DeepDocClient(settings.deepdoc).document_info(path, thumbnail=True)["thumbnail"]
    return _native().thumbnail_data_url(path, max_chars)
