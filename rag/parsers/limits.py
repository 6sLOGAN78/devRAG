"""Archive and XML guard run before any OOXML parser opens a file (R-161, T-04-09-01, T-04-09-02).

lxml defaults for entity resolution were not verified (A6), so the guard refuses a DOCTYPE or ENTITY
declaration outright instead of relying on parser settings. Messages never carry a member name or path.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from zlib import error as zlib_error

from rag.parsers.errors import ArchiveLimitsExceeded, FileDamaged

_XML_SUFFIXES = (".xml", ".rels")
_FORBIDDEN = (b"<!doctype", b"<!entity")


class _DeclarationNotAllowed(FileDamaged):
    message = "the file contains a declaration that is not allowed"


def check_ooxml_limits(
    path: Path,
    *,
    max_members: int = 2000,
    max_total: int = 200 * 2**20,
    max_member: int = 100 * 2**20,
    max_ratio: int = 200,
    max_xml_scan: int = 8 * 2**20,
) -> None:
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
                if not info.filename.lower().endswith(_XML_SUFFIXES):
                    continue
                with zf.open(info) as member:
                    head = member.read(max_xml_scan).lower()
                if any(token in head for token in _FORBIDDEN):
                    raise _DeclarationNotAllowed()
    except (zipfile.BadZipFile, OSError, EOFError, zlib_error, NotImplementedError, RuntimeError) as exc:
        raise FileDamaged() from exc
