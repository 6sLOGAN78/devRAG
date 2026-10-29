"""Bounded chunks stay within one original slide and repeat its title."""

from dataclasses import dataclass
from itertools import groupby
from rag.chunking.errors import ChunkTooLong
from rag.chunking.types import Chunk
from rag.nlp.token_count import count_tokens, split_at_tokens
from rag.parsers.errors import FileDamaged


@dataclass(frozen=True)
class PresentationConfig:
    chunk_token_num: int = 512


def chunk(blocks, cfg):
    index = 0
    previous = 0
    for slide, group in groupby(blocks, key=lambda b: b.slide):
        if slide is None or slide.number <= previous:
            raise FileDamaged()
        previous = slide.number
        items = list(group)
        prefix = slide.title + "\n" if slide.title else ""
        body = "\n".join(b.text for b in items if b.text.strip() != slide.title)
        limit = min(max(1, cfg.chunk_token_num), 8191)
        budget = limit - count_tokens(prefix)
        if budget < 1:
            raise ChunkTooLong()
        if not body.strip() and not prefix and not any(b.image_ids for b in items):
            continue
        parts = split_at_tokens(body, budget) if body else [""]
        while budget > 1 and any(count_tokens(prefix + p) > limit for p in parts):
            budget -= 1
            parts = split_at_tokens(body, budget)
        for part in parts:
            text = prefix + part
            if count_tokens(text) > limit:
                raise ChunkTooLong()
            yield Chunk(text, (), {}, count_tokens(text), index, tables=tuple(b.table for b in items if b.table), image_ids=tuple(dict.fromkeys(i for b in items for i in b.image_ids)), slide=slide)
            index += 1
