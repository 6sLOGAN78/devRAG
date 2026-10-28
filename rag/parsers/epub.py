"""EPUB container → OPF → spine order, with TOC ancestry and inert XHTML."""

from __future__ import annotations

import zipfile
from dataclasses import replace
from zlib import error as zlib_error

from rag.parsers.epub_archive import check_archive, resolve, xml
from rag.parsers.errors import FileDamaged, FileTooLarge, NoReadableText
from rag.parsers.html import parse_markup
from rag.parsers.sections import Section
from rag.parsers.types import ParseLimits

CONTAINER = "urn:oasis:names:tc:opendocument:xmlns:container"
OPF = "http://www.idpf.org/2007/opf"
HTML = "http://www.w3.org/1999/xhtml"
NCX = "http://www.daisy.org/z3986/2005/ncx/"
OPS = "http://www.idpf.org/2007/ops"
TEXT_TYPES = {"application/xhtml+xml", "text/html"}


def _label(node):
    value = " ".join("".join(node.itertext()).split())
    if not value or len(value) > 1024:
        raise FileDamaged()
    return value


def _toc(root, base):
    paths = {}

    def add(href, labels):
        if len(labels) > 26:
            raise FileTooLarge()
        paths.setdefault(resolve(base, href), labels)

    def nav(ol, parents):
        for item in ol.findall(f"{{{HTML}}}li"):
            label = next((n for n in item if n.tag in {f"{{{HTML}}}a", f"{{{HTML}}}span"}), None)
            if label is None:
                raise FileDamaged()
            labels = (*parents, _label(label))
            if len(labels) > 26:
                raise FileTooLarge()
            if label.get("href"):
                add(label.get("href"), labels)
            for child in item.findall(f"{{{HTML}}}ol"):
                nav(child, labels)

    def ncx(node, parents):
        for point in node.findall(f"{{{NCX}}}navPoint"):
            label = point.find(f"{{{NCX}}}navLabel/{{{NCX}}}text")
            content = point.find(f"{{{NCX}}}content")
            if label is None or content is None or not content.get("src"):
                raise FileDamaged()
            labels = (*parents, _label(label))
            add(content.get("src"), labels)
            ncx(point, labels)

    if root.tag == f"{{{NCX}}}ncx":
        node = root.find(f"{{{NCX}}}navMap")
        if node is None:
            raise FileDamaged()
        ncx(node, ())
    else:
        nodes = [n for n in root.iter(f"{{{HTML}}}nav") if "toc" in n.get(f"{{{OPS}}}type", "").split()]
        if len(nodes) != 1:
            raise FileDamaged()
        lists = nodes[0].findall(f"{{{HTML}}}ol")
        if len(lists) != 1:
            raise FileDamaged()
        nav(lists[0], ())
    return paths


def parse(source, report, *, page_range=None, limits=None):
    del page_range
    limits = limits or ParseLimits()
    blocks = []
    try:
        with zipfile.ZipFile(source.path) as zf:
            members = check_archive(zf)

            def read(path):
                if path not in members:
                    raise FileDamaged()
                return zf.read(members[path])

            if read("mimetype").strip() != b"application/epub+zip":
                raise FileDamaged()
            container = xml(read("META-INF/container.xml"))
            roots = container.findall(f"{{{CONTAINER}}}rootfiles/{{{CONTAINER}}}rootfile")
            if container.tag != f"{{{CONTAINER}}}container" or len(roots) != 1 or not roots[0].get("full-path"):
                raise FileDamaged()
            package_path = resolve("", roots[0].get("full-path"))
            package = xml(read(package_path))
            if package.tag != f"{{{OPF}}}package":
                raise FileDamaged()
            items = package.findall(f"{{{OPF}}}manifest/{{{OPF}}}item")
            manifest = {}
            for item in items:
                identifier, href = item.get("id"), item.get("href")
                if not identifier or identifier in manifest or not href:
                    raise FileDamaged()
                manifest[identifier] = (resolve(package_path, href), item)
            spines = package.findall(f"{{{OPF}}}spine")
            if len(spines) != 1:
                raise FileDamaged()
            spine = spines[0]
            navs = [pair for pair in manifest.values() if "nav" in pair[1].get("properties", "").split()]
            if len(navs) > 1:
                raise FileDamaged()
            toc = navs[0] if navs else manifest.get(spine.get("toc"))
            paths = _toc(xml(read(toc[0])), toc[0]) if toc else {}
            visited = set()
            visited_paths = set()
            total = 0
            refs = spine.findall(f"{{{OPF}}}itemref")
            if not refs:
                raise FileDamaged()
            for ref in refs:
                identifier = ref.get("idref")
                if identifier not in manifest or identifier in visited:
                    raise FileDamaged()
                visited.add(identifier)
                path, item = manifest[identifier]
                if path in visited_paths:
                    raise FileDamaged()
                visited_paths.add(path)
                if ref.get("linear", "yes") == "no":
                    continue
                if item.get("media-type") not in TEXT_TYPES:
                    raise FileDamaged()
                data = read(path)
                total += len(data)
                if total > limits.max_text_bytes:
                    raise FileTooLarge()
                root = xml(data)
                if root.tag != f"{{{HTML}}}html":
                    raise FileDamaged()
                try:
                    content = parse_markup(data)
                except NoReadableText:
                    continue
                parents = paths.get(path, ())
                headings = []
                for block in content:
                    if block.kind == "heading":
                        headings = [h for h in headings if h.heading_level < block.heading_level]
                        headings.append(block)
                    labels = list(parents)
                    for heading in headings:
                        if not labels or labels[-1] != heading.text:
                            labels.append(heading.text)
                    section = Section(tuple(labels), path)
                    blocks.append(replace(block, section=section))
    except (zipfile.BadZipFile, KeyError, OSError, EOFError, zlib_error, RuntimeError, NotImplementedError, ValueError):
        raise FileDamaged() from None
    if not blocks:
        raise NoReadableText()
    report.pages_total = None
    return iter(blocks)
