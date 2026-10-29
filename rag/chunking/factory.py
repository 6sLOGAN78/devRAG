"""Chunker factory (D-15, CHUNK-01): only built methods resolve; the others are refused, never replaced by naive."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import Any

from common.ingest_codes import IMPLEMENTED_PARSERS, METHOD_ORDER
from rag.chunking import naive, one, manual, qa, book, paper, laws, presentation, table
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


_CHUNKERS: dict[str, Chunker] = {"naive": naive.chunk, "one": one.chunk, "manual": manual.chunk, "qa": qa.chunk, "book": book.chunk, "paper": paper.chunk, "laws": laws.chunk, "presentation": presentation.chunk, "table": table.chunk}


def get_chunker(parser_id: str) -> Chunker:
    if parser_id not in IMPLEMENTED_PARSERS or parser_id not in _CHUNKERS:
        raise ChunkerUnavailable()
    return _CHUNKERS[parser_id]


def get_chunker_config(parser_id: str, raw: dict[str, Any]):
    """Each built method owns its configuration; unbuilt methods cannot borrow General."""
    get_chunker(parser_id)
    if parser_id == "table":
        return table.TableConfig(chunk_token_num=int(raw.get("chunk_token_num") or 512))
    if parser_id == "presentation":
        return presentation.PresentationConfig(chunk_token_num=int(raw.get("chunk_token_num") or 512))
    if parser_id == "laws":
        return laws.LawsConfig(chunk_token_num=int(raw.get("chunk_token_num") or 512))
    if parser_id == "paper":
        return paper.PaperConfig(chunk_token_num=int(raw.get("chunk_token_num") or 512))
    if parser_id == "book":
        return book.BookConfig(chunk_token_num=int(raw.get("chunk_token_num") or 512))
    if parser_id == "qa":
        return qa.QAConfig()
    if parser_id == "manual":
        return manual.ManualConfig(chunk_token_num=int(raw.get("chunk_token_num") or 512))
    if parser_id == "one":
        return one.OneConfig()
    if parser_id != "naive":
        raise ChunkerUnavailable()
    defaults = naive.NaiveConfig()
    delimiter = raw.get("delimiter")
    delimiter = delimiter.replace("\\n", "\n").replace("\\t", "\t") if isinstance(delimiter, str) and delimiter else defaults.delimiter
    return naive.NaiveConfig(
        chunk_token_num=int(raw.get("chunk_token_num") or defaults.chunk_token_num), delimiter=delimiter,
        overlapped_percent=int(raw.get("overlapped_percent") or defaults.overlapped_percent),
    )
