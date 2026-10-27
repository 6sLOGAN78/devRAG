"""Page images, original bytes and decoded text previews of stored documents (plan 04-20; DOC-21, PARSE-03, UI-16, UI-19).

* ``page_image`` renders page ``n`` (1-based) of a PDF at zoom 3 through the parser's own ``rasterize_page`` (same page box, rotation and render
  pixel budget as the boxes the parser stores) and answers JPEG bytes with a content-hash ETag. The stored PDF is read from a small bounded
  temp-file cache (``PdfFileCache``), so flipping pages does not download the file again.
* ``content_stream`` gives the original bytes in chunks. The type is decided here from the stored extension, never from the upload: only PDF, PNG
  and JPEG are inline, HTML and every unknown type are served as ``application/octet-stream`` attachments.
* ``content_text`` decodes at most ``text_preview_chars`` characters of a text-like file.

Every function takes a ``VisibleDataset`` (the caller already passed the visibility rule) and answers the one ``NOT_FOUND`` for a document that is
absent or belongs to another dataset. Functions block (database, storage, pdfium): the caller runs them in a bounded executor with a deadline.
"""

from __future__ import annotations

import io
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from api.db.database import DB
from api.db.models import Document
from api.db.services.knowledgebase_service import VisibleDataset
from api.db.services.pdf_pages import PDF_CACHE, PdfFileCache
from api.db.services.service_errors import Kind, ServiceError
from api.utils import reasons
from common.constants import BUCKET_NAME
from common.settings import Settings
from rag.parsers.deepdoc_client import DeepDocClient, NativeUnavailable
from rag.parsers.errors import ParserError
from rag.parsers.pdf import count_pages, rasterize_page
from rag.parsers.txt import decode_text
from rag.utils.storage_base import Storage, StorageError, StorageNotFound
from rag.utils.storage_factory import get_storage

logger = logging.getLogger(__name__)

ZOOM = 3.0
JPEG_QUALITY = 80
_ID = re.compile(r"[0-9a-f]{32}")
_INLINE_TYPES = {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}
_ATTACHMENT_TYPES = {"txt": "text/plain", "md": "text/markdown", "markdown": "text/markdown", "csv": "text/csv", "json": "application/json"}
_TEXT_SUFFIXES = frozenset({"txt", "md", "markdown", "csv", "json", "html", "htm"})
_OCTET = "application/octet-stream"
_UNSAFE_NAME = re.compile(r'[\x00-\x1f\x7f"\\/;]')
MAX_NAME_CHARS = 200


@dataclass(frozen=True)
class RenderedPage:
    data: bytes
    etag: str


@dataclass
class ContentStream:
    chunks: Iterator[bytes]
    size: int | None
    content_type: str
    filename: str
    inline: bool

    def close(self) -> None:
        close = getattr(self.chunks, "close", None)
        if close is not None:
            close()


def _not_found() -> ServiceError:
    return ServiceError(Kind.NOT_FOUND, reasons.DATASET_NOT_FOUND, "not found")


def _unavailable() -> ServiceError:
    return ServiceError(Kind.INVALID, reasons.PREVIEW_UNAVAILABLE, "this document cannot be previewed")


def _storage_error(exc: StorageError) -> ServiceError:
    if isinstance(exc, StorageNotFound):
        return _not_found()
    return ServiceError(Kind.UNAVAILABLE, reasons.STORAGE_UNAVAILABLE, "the file store is not available")


def safe_filename(name: str | None) -> str:
    """A file name safe for a header: last path segment, no quotes, separators or control characters, never empty."""
    last = re.split(r"[\\/]", name or "")[-1]
    cleaned = _UNSAFE_NAME.sub("", last).strip(". ")
    return cleaned[:MAX_NAME_CHARS] or "download"


def _load(visible: VisibleDataset, doc_id: str) -> Document:
    if not isinstance(doc_id, str) or _ID.fullmatch(doc_id) is None:
        raise _not_found()
    with DB.connection_context():
        doc = (
            Document.select(Document.id, Document.name, Document.suffix, Document.location, Document.content_hash, Document.size)
            .where((Document.id == doc_id) & (Document.kb_id == visible.dataset.id))
            .first()
        )
    if doc is None:
        raise _not_found()
    return doc


def _pdf_of(visible: VisibleDataset, doc_id: str, n: int) -> Document:
    doc = _load(visible, doc_id)
    if (doc.suffix or "").lower() != "pdf" or not doc.location or not isinstance(n, int) or n < 1:
        raise _not_found()
    return doc


def _etag(doc: Document, n: int) -> str:
    return f'"{doc.content_hash or ""}:{n}:{int(ZOOM)}"'


def page_etag(settings: Settings, visible: VisibleDataset, doc_id: str, n: int, *, storage: Storage | None = None, cache: PdfFileCache | None = None) -> str | None:
    """The ETag page ``n`` would carry, without rendering it; ``None`` when it cannot be known (the caller then renders and gets the typed error)."""
    doc = _pdf_of(visible, doc_id, n)
    blobs = storage if storage is not None else get_storage(settings)
    try:
        path = (cache or PDF_CACHE).path_for(blobs, doc.location, doc.content_hash or "")
        total = count_pages(path, settings=settings)
    except NativeUnavailable:
        raise ServiceError(Kind.UNAVAILABLE, reasons.PREVIEW_UNAVAILABLE, "the preview service is not available") from None
    except (StorageError, ParserError):
        return None
    return _etag(doc, n) if n <= total else None


def page_image(settings: Settings, visible: VisibleDataset, doc_id: str, n: int, *, storage: Storage | None = None, cache: PdfFileCache | None = None) -> RenderedPage:
    """Page ``n`` (1-based) of a PDF as a JPEG. ``NOT_FOUND`` beyond the last page and for any other type; 400 ``preview_unavailable`` for a damaged file."""
    doc = _pdf_of(visible, doc_id, n)
    blobs = storage if storage is not None else get_storage(settings)
    files = cache or PDF_CACHE
    for attempt in (1, 2):
        path = None
        try:
            path = files.path_for(blobs, doc.location, doc.content_hash or "")
            total = count_pages(path, settings=settings)
            if n > total:
                raise _not_found()
            if settings.deepdoc.url:
                data = DeepDocClient(settings.deepdoc).page_image(path, n, ZOOM)
                return RenderedPage(data, _etag(doc, n))
            image = rasterize_page(path, n - 1, ZOOM).convert("RGB")
            break
        except StorageError as exc:
            raise _storage_error(exc) from None
        except NativeUnavailable:
            raise ServiceError(Kind.UNAVAILABLE, reasons.PREVIEW_UNAVAILABLE, "the preview service is not available") from None
        except ParserError:
            if attempt == 1 and path is not None and not path.exists():
                continue  # evicted by a concurrent request between the lookup and the open
            logger.warning("page render failed document=%s page=%d", doc.id, n)
            raise _unavailable() from None
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=JPEG_QUALITY)
    return RenderedPage(buffer.getvalue(), _etag(doc, n))


def content_stream(settings: Settings, visible: VisibleDataset, doc_id: str, *, storage: Storage | None = None) -> ContentStream:
    """The stored bytes of a document, lazily, with the size and a safe type. The caller closes the stream (also when the client leaves)."""
    doc = _load(visible, doc_id)
    if not doc.location:
        raise _not_found()
    blobs = storage if storage is not None else get_storage(settings)
    suffix = (doc.suffix or "").lower()
    try:
        size = blobs.size(BUCKET_NAME, doc.location)
        if size is None:
            raise _not_found()
        chunks = blobs.iter_chunks(BUCKET_NAME, doc.location)
    except StorageError as exc:
        raise _storage_error(exc) from None
    inline_type = _INLINE_TYPES.get(suffix)
    return ContentStream(
        chunks=chunks,
        size=size,
        content_type=inline_type or _ATTACHMENT_TYPES.get(suffix) or _OCTET,
        filename=safe_filename(doc.name),
        inline=inline_type is not None,
    )


def _decode_prefix(data: bytes, byte_cut: bool) -> str:
    if byte_cut:  # a cut can end inside a multi-byte character
        for drop in range(4):
            try:
                return (data[: len(data) - drop] if drop else data).decode("utf-8-sig")
            except UnicodeDecodeError:
                continue
    return decode_text(data)


def content_text(settings: Settings, visible: VisibleDataset, doc_id: str, *, storage: Storage | None = None) -> dict[str, Any]:
    """``{text, cut}`` of a text-like file: the first ``text_preview_chars`` characters, HTML as its source. 400 ``preview_unavailable`` otherwise."""
    doc = _load(visible, doc_id)
    if (doc.suffix or "").lower() not in _TEXT_SUFFIXES or not doc.location:
        raise _unavailable()
    limit = settings.ingest.text_preview_chars
    wanted = limit * 4 + 4
    blobs = storage if storage is not None else get_storage(settings)
    data = bytearray()
    stream = blobs.iter_chunks(BUCKET_NAME, doc.location)
    try:
        for piece in stream:
            data.extend(piece)
            if len(data) > wanted:
                break
    except StorageError as exc:
        raise _storage_error(exc) from None
    finally:
        close = getattr(stream, "close", None)
        if close is not None:
            close()
    byte_cut = len(data) > wanted
    try:
        text = _decode_prefix(bytes(data[:wanted]), byte_cut)
    except ParserError:
        raise _unavailable() from None
    return {"text": text[:limit], "cut": byte_cut or len(text) > limit}
