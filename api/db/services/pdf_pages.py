"""PDF page count with a small per-document cache (plan 04-15; UI-SPEC note 6, T-04-15-05).

The count is cached per ``(document id, content hash)``, so a re-upload of different bytes under the same id would miss. Only a successful
count or a damaged file is cached; a storage failure is not, so the next call tries again. Drivers are blocking: the caller runs this in the
storage executor with a deadline.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import tempfile
import threading
from collections import OrderedDict
from pathlib import Path

from api.db.services.service_errors import Kind, ServiceError
from api.utils import reasons
from common.constants import BUCKET_NAME
from common.settings import Settings
from rag.parsers.deepdoc_client import NativeUnavailable
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
    key = (doc_id, f"{content_hash or ''}:{settings.deepdoc.url}")
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
            total = count_pages(path, settings=settings)
        except NativeUnavailable:
            # A service outage is never remembered as a damaged document.
            raise ServiceError(Kind.UNAVAILABLE, reasons.PARSE_UNAVAILABLE, "the native parsing service is not available") from None
        except ParserError:
            _remember(key, _DAMAGED)
            return None
    _remember(key, total)
    return total


class PdfFileCache:
    """A small on-disk cache of stored PDFs so that flipping pages does not download the file again (plan 04-20, T-04-20-04).

    Keyed by ``(location, content hash)``. File names are ``sha256(location|hash).hex() + ".pdf"``: nothing a user supplies reaches a path. The
    directory is created lazily with mode 0700. At most ``max_files`` files and ``max_bytes`` bytes are kept; the least recently used file is
    deleted from disk first, and the newest file is always kept so the caller that just fetched it can open it. One lock covers a download, so
    two threads asking for the same file fetch it once.
    """

    def __init__(self, max_files: int = 4, max_bytes: int = 400 * 1024 * 1024) -> None:
        self.max_files = max_files
        self.max_bytes = max_bytes
        self._lock = threading.Lock()
        self._files: OrderedDict[tuple[str, str], tuple[Path, int]] = OrderedDict()
        self._dir: Path | None = None

    def _directory(self) -> Path:
        if self._dir is None:
            self._dir = Path(tempfile.mkdtemp(prefix="devrag-pdf-"))
            self._dir.chmod(0o700)
        return self._dir

    def paths(self) -> list[Path]:
        """Cached files, least recently used first."""
        with self._lock:
            return [entry[0] for entry in self._files.values()]

    def clear(self) -> None:
        with self._lock:
            for path, _size in self._files.values():
                path.unlink(missing_ok=True)
            self._files.clear()
            if self._dir is not None:
                shutil.rmtree(self._dir, ignore_errors=True)
                self._dir = None

    def _evict(self) -> None:
        while len(self._files) > 1 and (len(self._files) > self.max_files or sum(size for _p, size in self._files.values()) > self.max_bytes):
            _key, (path, _size) = self._files.popitem(last=False)
            path.unlink(missing_ok=True)

    def path_for(self, storage: Storage, location: str, content_hash: str) -> Path:
        """The local copy of the stored PDF, downloading it on a miss. Raises ``StorageError`` (``StorageNotFound`` when absent)."""
        key = (location, content_hash or "")
        with self._lock:
            hit = self._files.get(key)
            if hit is not None and hit[0].exists():
                self._files.move_to_end(key)
                return hit[0]
            name = hashlib.sha256(f"{location}|{content_hash or ''}".encode()).hexdigest() + ".pdf"
            target = self._directory() / name
            partial = target.with_suffix(".part")
            size = 0
            stream = storage.iter_chunks(BUCKET_NAME, location)
            try:
                with partial.open("wb") as handle:
                    for piece in stream:
                        handle.write(piece)
                        size += len(piece)
                partial.replace(target)
            except BaseException:
                partial.unlink(missing_ok=True)
                raise
            finally:
                close = getattr(stream, "close", None)
                if close is not None:
                    close()
            self._files[key] = (target, size)
            self._files.move_to_end(key)
            self._evict()
            return target


PDF_CACHE = PdfFileCache()
