"""Read only in-package image relationships; native normalization stays remote."""

from __future__ import annotations

import hashlib
import posixpath
import zipfile
from dataclasses import replace
from urllib.parse import unquote, urlsplit

from lxml import etree as ElementTree

from common.settings import Settings
from rag.parsers.assets import MAX_ASSETS, ParsedAsset
from rag.parsers.deepdoc_client import DeepDocClient
from rag.parsers.errors import FileDamaged, FileTooLarge

_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


class OOXMLImages:
    def __init__(self, path, settings: Settings | None):
        self.enabled = settings is not None and bool(settings.deepdoc.url)
        self.archive = zipfile.ZipFile(path) if self.enabled else None
        self.client = DeepDocClient(settings.deepdoc) if self.enabled else None
        self.relationships: dict[str, dict[str, str]] = {}
        self.normalized: dict[str, ParsedAsset] = {}
        self.count = 0
        self.total_bytes = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self.archive is not None:
            self.archive.close()

    def _relations(self, part: str) -> dict[str, str]:
        if part in self.relationships:
            return self.relationships[part]
        folder, name = posixpath.split(part)
        rel_path = posixpath.join(folder, "_rels", name + ".rels")
        try:
            root = ElementTree.fromstring(
                self.archive.read(rel_path),
                parser=ElementTree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False),
            )
        except (KeyError, ElementTree.XMLSyntaxError):
            raise FileDamaged() from None
        result = {}
        for rel in root:
            if not rel.attrib.get("Type", "").endswith("/image"):
                continue
            target = unquote(rel.attrib.get("Target", ""))
            url = urlsplit(target)
            if rel.attrib.get("TargetMode", "").lower() == "external" or url.scheme or url.netloc or url.query or url.fragment or "\\" in target:
                raise FileDamaged()
            normalized = posixpath.normpath(target.lstrip("/") if target.startswith("/") else posixpath.join(folder, target))
            if normalized in {"", ".", ".."} or normalized.startswith("../") or normalized not in self.archive.namelist():
                raise FileDamaged()
            result[rel.attrib.get("Id", "")] = normalized
        self.relationships[part] = result
        return result

    def for_element(self, element, part: str, caption: str = "") -> tuple[ParsedAsset, ...]:
        if not self.enabled:
            return ()
        refs = []
        for node in element.iter():
            if node.tag.rsplit("}", 1)[-1] not in {"blip", "imagedata"}:
                continue
            if node.attrib.get(_R + "link"):
                raise FileDamaged()
            ref = node.attrib.get(_R + "embed") or node.attrib.get(_R + "id")
            if ref:
                refs.append(ref)
        if not refs:
            return ()
        relations = self._relations(part.lstrip("/"))
        assets = []
        for ref in refs:
            self.count += 1
            if self.count > MAX_ASSETS:
                raise FileTooLarge()
            target = relations.get(ref)
            if target is None:
                raise FileDamaged()
            info = self.archive.getinfo(target)
            if info.file_size > 16 * 1024 * 1024:
                raise FileTooLarge()
            raw = self.archive.read(target)
            digest = hashlib.sha256(raw).hexdigest()
            if digest not in self.normalized:
                normalized = self.client.normalize_image(raw)
                self.total_bytes += len(normalized.content)
                if self.total_bytes > 24 * 1024 * 1024:
                    raise FileTooLarge()
                self.normalized[digest] = normalized
            assets.append(replace(self.normalized[digest], caption=caption[:1024]))
        return tuple(assets)
