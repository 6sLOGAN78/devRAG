"""Book sections stay in source order; repeat parent labels on bounded prose chunks."""

from __future__ import annotations

from dataclasses import dataclass

from rag.chunking.errors import ChunkTooLong
from rag.chunking.types import Chunk
from rag.nlp.token_count import count_tokens, split_at_tokens
from rag.parsers.sections import Section

HARD_CONTEXT = 8191


@dataclass(frozen=True)
class BookConfig:
    chunk_token_num: int = 512


def chunk(blocks, cfg: BookConfig):
    index = 0
    headings = []
    pending = []
    current = None

    def emit(group, section):
        nonlocal index
        if not group:
            return
        prefix = "\n".join(section.path)
        prefix = prefix + "\n" if prefix else ""
        body = "\n".join(block.text for block in group if block.kind != "heading")
        if not body.strip() and not prefix:
            return
        limit = max(1, min(cfg.chunk_token_num, HARD_CONTEXT))
        budget = limit - count_tokens(prefix)
        if budget < 1:
            raise ChunkTooLong()
        atomic = any(b.kind in {"table", "code", "image"} for b in group)
        pieces = [body]
        if not atomic and count_tokens(prefix + body) > limit:
            pieces = split_at_tokens(body, budget)
            while budget > 1 and any(count_tokens(prefix + part) > limit for part in pieces):
                budget -= 1
                pieces = split_at_tokens(body, budget)
        for part in pieces:
            text = prefix + part
            tokens = count_tokens(text)
            if tokens > HARD_CONTEXT or (not atomic and tokens > limit):
                raise ChunkTooLong()
            yield Chunk(
                text, tuple(box for b in group for box in b.boxes),
                {p: size for b in group for p, size in b.page_sizes.items()}, tokens, index,
                tables=tuple(b.table for b in group if b.table is not None),
                image_ids=tuple(dict.fromkeys(i for b in group for i in b.image_ids)),
                source_lines=tuple(b.line_range for b in group if b.line_range is not None),
                sections=(section,),
            )
            index += 1

    for block in blocks:
        if block.section is not None:
            section = block.section
        else:
            if block.kind == "heading":
                level = block.heading_level or 1
                headings = [h for h in headings if (h.heading_level or 1) < level]
                headings.append(block)
            section = Section(tuple(h.text.strip() for h in headings))
        if current is not None and section != current and any(b.kind != "heading" for b in pending):
            yield from emit(pending, current)
            pending = []
        current = section
        pending.append(block)
    if current is not None:
        yield from emit(pending, current)
