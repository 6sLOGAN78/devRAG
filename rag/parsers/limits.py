"""Archive and XML guard run before any OOXML parser opens a file (R-161, T-04-09-01, T-04-09-02).

lxml defaults for entity resolution were not verified (A6), so the guard refuses a DOCTYPE or ENTITY
declaration outright instead of relying on parser settings. Messages never carry a member name or path.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from zlib import error as zlib_error

from rag.parsers.errors import ArchiveLimitsExceeded, FileDamaged

_FORBIDDEN = (b"<!doctype", b"<!entity")
_CHUNK = 1024 * 1024
_OVERLAP = max(len(token) for token in _FORBIDDEN) - 1
_HEAD = 4096
_UTF8_BOM = b"\xef\xbb\xbf"
# UTF-16 / UTF-32 byte order marks, and the shape of "<" in those encodings with and without a mark.
_WIDE_BOMS = (b"\xff\xfe", b"\xfe\xff", b"\x00\x00\xfe\xff")
_WIDE_LT = (b"<\x00", b"\x00<")
_DECL_ENCODING = re.compile(rb"^<\?xml[^>]*?encoding\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
_ALLOWED_ENCODINGS = (b"utf-8", b"us-ascii")


class _DeclarationNotAllowed(FileDamaged):
    message = "the file contains a declaration that is not allowed"


def check_ooxml_limits(
    path: Path,
    *,
    max_members: int = 2000,
    max_total: int = 200 * 2**20,
    max_member: int = 100 * 2**20,
    max_ratio: int = 200,
) -> None:
    """Refuse archives over the limits, and any XML-looking member (by content, not name) that is not plain UTF-8 or declares a DTD/entity.

    UTF-16/32 parts are rejected rather than decoded (OOXML producers write UTF-8 in practice; R-168). Every member is read through in
    1 MiB windows overlapping by ``len(longest token) - 1``; total work is bounded by ``max_member`` / ``max_total``.
    """
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
            if len(infos) > max_members:
                raise ArchiveLimitsExceeded()
            total = 0
            for info in infos:
                total += info.file_size
                if info.file_size > max_member or total > max_total:
                    raise ArchiveLimitsExceeded()
                if info.compress_size > 0 and info.file_size / info.compress_size > max_ratio:
                    raise ArchiveLimitsExceeded()
                if info.compress_size == 0 and info.file_size > 0:
                    raise ArchiveLimitsExceeded()
            for info in infos:
                if info.is_dir() or info.file_size == 0:
                    continue
                with zf.open(info) as member:
                    _scan_member(member)
    except (zipfile.BadZipFile, OSError, EOFError, zlib_error, NotImplementedError, RuntimeError) as exc:
        raise FileDamaged() from exc


def _is_wide_xml(head: bytes) -> bool:
    if head.startswith(_WIDE_BOMS):
        return True
    return head.startswith(_WIDE_LT) or head.startswith(b"\x00\x00\x00<") or head.startswith(b"<\x00\x00\x00")


def _looks_like_xml(head: bytes) -> bool:
    if head.startswith(_UTF8_BOM):
        head = head[len(_UTF8_BOM) :]
    return head.lstrip(b" \t\r\n").startswith(b"<")


def _scan_member(member) -> None:  # noqa: ANN001 - file-like ZipExtFile
    head = member.read(_HEAD)
    if _is_wide_xml(head):
        raise _DeclarationNotAllowed()
    if not _looks_like_xml(head):
        return
    stripped = head[len(_UTF8_BOM) :] if head.startswith(_UTF8_BOM) else head
    declared = _DECL_ENCODING.match(stripped.lstrip(b" \t\r\n"))
    if declared and declared.group(1).strip().lower() not in _ALLOWED_ENCODINGS:
        raise _DeclarationNotAllowed()
    window = head
    while True:
        lowered = window.lower()
        if any(token in lowered for token in _FORBIDDEN):
            raise _DeclarationNotAllowed()
        chunk = member.read(_CHUNK)
        if not chunk:
            return
        window = window[-_OVERLAP:] + chunk
