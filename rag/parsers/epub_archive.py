"""Safe EPUB member addressing and bounded UTF-8 XML; never extract or fetch."""

from __future__ import annotations

import io
import posixpath
import stat
from urllib.parse import unquote, urlsplit

from lxml import etree

from rag.parsers.errors import ArchiveLimitsExceeded, FileDamaged
from rag.parsers.limits import _scan_member

MAX_DEPTH = 64
MAX_NODES = 100000


def member_path(name: str) -> str:
    decoded = unquote(name)
    if not decoded or decoded.startswith("/") or "\\" in decoded or "\x00" in decoded or len(decoded) > 4096:
        raise FileDamaged()
    if any(part in {"", ".", ".."} for part in decoded.rstrip("/").split("/")):
        raise FileDamaged()
    return decoded.rstrip("/")


def resolve(base: str, href: str) -> str:
    uri = urlsplit(href)
    if uri.scheme or uri.netloc or uri.query:
        raise FileDamaged()
    path = unquote(uri.path)
    if "\\" in path or "\x00" in path or path.startswith("/"):
        raise FileDamaged()
    target = posixpath.normpath(posixpath.join(posixpath.dirname(base), path)) if path else base
    return member_path(target)


def xml(data: bytes):
    _scan_member(io.BytesIO(data))
    try:
        parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True, recover=False, huge_tree=False)
        root = etree.fromstring(data, parser)
        stack = [(root, 1)]
        nodes = 0
        while stack:
            node, depth = stack.pop()
            nodes += 1
            if depth > MAX_DEPTH or nodes > MAX_NODES:
                raise ArchiveLimitsExceeded()
            stack.extend((child, depth + 1) for child in node)
        return root
    except (etree.XMLSyntaxError, ValueError):
        raise FileDamaged() from None


def check_archive(zf) -> dict[str, str]:
    infos = zf.infolist()
    if len(infos) > 2000 or sum(info.file_size for info in infos) > 200 * 2**20:
        raise ArchiveLimitsExceeded()
    members = {}
    for info in infos:
        name = member_path(info.filename)
        if name in members or stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1:
            raise FileDamaged()
        if info.file_size > 100 * 2**20 or (info.file_size and (not info.compress_size or info.file_size / info.compress_size > 200)):
            raise ArchiveLimitsExceeded()
        members[name] = info.filename
    # Scan every member, including unused markup, under the expansion bounds above.
    for info in infos:
        if info.is_dir():
            continue
        with zf.open(info) as handle:
            _scan_member(handle)
        if info.filename.lower().endswith((".xml", ".opf", ".ncx", ".xhtml")):
            xml(zf.read(info))
    return members
