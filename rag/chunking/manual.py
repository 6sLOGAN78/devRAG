"""Section-aware manuals: keep code, parameter tables and diagram descriptors atomic."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from rag.chunking.errors import ChunkTooLong
from rag.chunking.types import Chunk
from rag.nlp.token_count import count_tokens, split_at_tokens
from rag.parsers.types import ParsedBlock

HARD_CONTEXT = 8191


@dataclass(frozen=True)
class ManualConfig:
    chunk_token_num: int = 512  # Soft prose budget; structural groups remain atomic.


def chunk(blocks: Iterable[ParsedBlock], cfg: ManualConfig) -> Iterator[Chunk]:
    ancestry: list[ParsedBlock] = []
    section: list[ParsedBlock] = []
    parents: tuple[ParsedBlock, ...] = ()
    index = 0

    def emit(group, ancestors):
        nonlocal index
        headings = [block for block in group if block.kind == "heading"]
        prefix = "\n".join(block.text for block in [*ancestors, *headings])
        if prefix:
            prefix += "\n"
        body = "\n".join(block.text for block in group if block.kind != "heading")
        text = prefix + body
        if not text.strip():
            return
        atomic = any(block.kind in {"code", "table", "image"} for block in group)
        if atomic and count_tokens(text) > HARD_CONTEXT:
            raise ChunkTooLong()
        pieces = [body]
        if not atomic and count_tokens(text) > cfg.chunk_token_num:
            budget = max(1, min(cfg.chunk_token_num, HARD_CONTEXT) - count_tokens(prefix))
            pieces = split_at_tokens(body, budget)
            while budget > 1 and any(count_tokens(prefix + part) > cfg.chunk_token_num for part in pieces):
                budget -= 1
                pieces = split_at_tokens(body, budget)
        all_blocks = [*ancestors, *group]
        positions = tuple(box for block in all_blocks for box in block.boxes)
        sizes = {page: size for block in all_blocks for page, size in block.page_sizes.items()}
        tables = tuple(block.table for block in all_blocks if block.table is not None)
        images = tuple(dict.fromkeys(identifier for block in all_blocks for identifier in block.image_ids))
        source_lines = tuple(block.line_range for block in all_blocks if block.line_range is not None)
        for part in pieces:
            content = prefix + part
            tokens = count_tokens(content)
            if tokens > HARD_CONTEXT:
                raise ChunkTooLong()
            yield Chunk(content, positions, sizes, tokens, index, tables=tables, image_ids=images, source_lines=source_lines)
            index += 1

    for block in blocks:
        if block.kind == "heading":
            if section and any(item.kind != "heading" for item in section):
                yield from emit(section, parents)
            level = block.heading_level or 1
            ancestry = [item for item in ancestry if (item.heading_level or 1) < level]
            parents = tuple(ancestry)
            ancestry.append(block)
            section = [block]
        else:
            section.append(block)
    if section:
        yield from emit(section, parents)
