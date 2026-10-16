"""Chunker factory (D-15, CHUNK-01): only built methods resolve; the others are refused, never replaced by naive."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import Any

from common.ingest_codes import IMPLEMENTED_PARSERS, METHOD_ORDER
from rag.chunking import naive
from rag.chunking.types import Chunk
from rag.parsers.types import ParsedBlock

METHODS: tuple[str, ...] = METHOD_ORDER

Chunker = Callable[[Iterable[ParsedBlock], Any], Iterator[Chunk]]


class ChunkerUnavailable(Exception):
    code = "chunker_unavailable"

    def __init__(self) -> None:
        super().__init__("this chunking method is not available")


def available(method: str) -> bool:
    return method in IMPLEMENTED_PARSERS and method in _CHUNKERS


_CHUNKERS: dict[str, Chunker] = {"naive": naive.chunk}


def get_chunker(parser_id: str) -> Chunker:
    if parser_id not in IMPLEMENTED_PARSERS or parser_id not in _CHUNKERS:
        raise ChunkerUnavailable()
    return _CHUNKERS[parser_id]
