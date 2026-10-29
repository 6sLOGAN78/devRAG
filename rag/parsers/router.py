"""Suffix to parser table: the single answer to "can this file be parsed" (D-13, PARSE-01).

Loaders are dotted module paths imported lazily, so importing the router never imports pypdfium2 or lxml.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from types import ModuleType

from rag.parsers.errors import UnsupportedType


@dataclass(frozen=True)
class ParserSpec:
    name: str
    suffixes: frozenset[str]
    loader: str

    def load(self) -> ModuleType:
        return importlib.import_module(self.loader)


PARSERS: tuple[ParserSpec, ...] = (
    ParserSpec("email", frozenset({"eml"}), "rag.parsers.email"),
    ParserSpec("audio", frozenset({"wav", "mp3"}), "rag.parsers.audio"),
    ParserSpec("image",frozenset({"png","jpg","jpeg"}),"rag.parsers.image"),
    ParserSpec("pdf", frozenset({"pdf"}), "rag.parsers.pdf"),
    ParserSpec("docx", frozenset({"docx"}), "rag.parsers.docx"),
    ParserSpec("xlsx", frozenset({"xlsx"}), "rag.parsers.xlsx"),
    ParserSpec("pptx", frozenset({"pptx"}), "rag.parsers.pptx"),
    ParserSpec("html", frozenset({"html", "htm"}), "rag.parsers.html"),
    ParserSpec("markdown", frozenset({"md", "markdown"}), "rag.parsers.markdown"),
    ParserSpec("json", frozenset({"json"}), "rag.parsers.json"),
    ParserSpec("csv", frozenset({"csv"}), "rag.parsers.csv"),
    ParserSpec("epub", frozenset({"epub"}), "rag.parsers.epub"),
    ParserSpec("txt", frozenset({"txt"}), "rag.parsers.txt"),
)

_BY_SUFFIX: dict[str, ParserSpec] = {suffix: spec for spec in PARSERS for suffix in spec.suffixes}
PARSEABLE_SUFFIXES: frozenset[str] = frozenset(_BY_SUFFIX)


def _clean(suffix: str) -> str:
    return suffix.strip().lstrip(".").lower()


def parseable(suffix: str) -> bool:
    return _clean(suffix) in _BY_SUFFIX


def parser_for_suffix(suffix: str) -> ParserSpec:
    spec = _BY_SUFFIX.get(_clean(suffix))
    if spec is None:
        raise UnsupportedType()
    return spec
