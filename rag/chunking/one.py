"""Exactly one chunk for all selected document content; never truncate or split."""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from rag.chunking.errors import ChunkTooLong
from rag.chunking.types import Chunk
from rag.nlp.token_count import count_tokens
from rag.parsers.types import ParsedBlock


@dataclass(frozen=True)
class OneConfig:
    max_tokens: int = 8191  # Every current embedding driver has this absolute ceiling.


def chunk(blocks: Iterable[ParsedBlock], cfg: OneConfig) -> Iterator[Chunk]:
    texts, positions, tables, image_ids = [], [], [], []
    sizes = {}
    source_lines = []
    total_bytes = 0
    for block in blocks:
        total_bytes += len(block.text.encode("utf-8"))
        if total_bytes > 100 * 1024 * 1024:
            raise ChunkTooLong()
        if block.text.strip():
            texts.append(block.text)
        positions.extend(block.boxes)
        if block.line_range is not None:
            source_lines.append(block.line_range)
        sizes.update(block.page_sizes)
        if block.table is not None:
            tables.append(block.table)
        for identifier in block.image_ids:
            if identifier not in image_ids:
                image_ids.append(identifier)
    text = "\n".join(texts)
    if not text.strip():
        return
    tokens = count_tokens(text)
    if tokens > cfg.max_tokens:
        raise ChunkTooLong()
    yield Chunk(text, tuple(positions), sizes, tokens, 0, tables=tuple(tables), image_ids=tuple(image_ids), source_lines=tuple(source_lines))
