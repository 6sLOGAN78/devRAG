"""Bounded message body chunks repeat the actual decoded envelope and MIME provenance."""

from dataclasses import dataclass
from rag.chunking.types import Chunk
from rag.chunking.errors import ChunkTooLong
from rag.nlp.token_count import count_tokens, split_at_tokens
from rag.parsers.errors import NoReadableText


@dataclass(frozen=True)
class EmailConfig:
    chunk_token_num: int = 512


def chunk(blocks, cfg):
    index = 0
    target = min(cfg.chunk_token_num, 8191)
    for block in blocks:
        if block.email is None or not block.text.strip() or block.boxes:
            raise NoReadableText()
        prefix = block.email.prefix()
        budget = target - count_tokens(prefix)
        if budget < 1:
            raise ChunkTooLong()
        pieces = split_at_tokens(block.text, budget)
        while budget > 1 and any(count_tokens(prefix + text) > target for text in pieces):
            budget -= 1
            pieces = split_at_tokens(block.text, budget)
        for text in pieces:
            content = prefix + text
            tokens = count_tokens(content)
            if tokens > target:
                raise ChunkTooLong()
            yield Chunk(content, (), {}, tokens, index)
            index += 1
