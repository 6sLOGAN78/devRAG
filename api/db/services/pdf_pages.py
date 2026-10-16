"""PDF page count with a small per-document cache (plan 04-15; UI-SPEC note 6, T-04-15-05).

The count is cached per ``(document id, content hash)``, so a re-upload of different bytes under the same id would miss. Only a successful
count or a damaged file is cached; a storage failure is not, so the next call tries again. Drivers are blocking: the caller runs this in the
storage executor with a deadline.
"""

from __future__ import annotations

import logging
import tempfile
import threading
from collections import OrderedDict
from pathlib import Path

from common.constants import BUCKET_NAME
from common.settings import Settings
from rag.parsers.errors import ParserError
from rag.parsers.pdf import count_pages
from rag.utils.storage_base import Storage, StorageError
from rag.utils.storage_factory import get_storage

logger = logging.getLogger(__name__)

CACHE_SIZE = 256
_DAMAGED = -1
_cache: OrderedDict[tuple[str, str], int] = OrderedDict()
_lock = threading.Lock()


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def _remember(key: tuple[str, str], value: int) -> None:
    with _lock:
        _cache[key] = value
        _cache.move_to_end(key)
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)


def pdf_page_count(settings: Settings, doc_id: str, location: str, content_hash: str, suffix: str, *, storage: Storage | None = None) -> int | None:
    """The number of pages of a PDF, or ``None`` for another type, a damaged file or an unreadable blob."""
    if (suffix or "").lower() != "pdf" or not location:
        return None
    key = (doc_id, content_hash or "")
    with _lock:
        hit = _cache.get(key)
        if hit is not None:
            _cache.move_to_end(key)
    if hit is not None:
        return None if hit == _DAMAGED else hit
    blobs = storage if storage is not None else get_storage(settings)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "doc.pdf"
        stream = blobs.iter_chunks(BUCKET_NAME, location)
        try:
            with path.open("wb") as handle:
                for piece in stream:
                    handle.write(piece)
        except StorageError:
            logger.warning("page count could not read the blob document=%s", doc_id)
            return None
        finally:
            close = getattr(stream, "close", None)
            if close is not None:
                close()
        try:
            total = count_pages(path)
        except ParserError:
            _remember(key, _DAMAGED)
            return None
    _remember(key, total)
    return total
