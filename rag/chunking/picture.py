"""One real image caption or explicit OCR text linked to owned image assets."""

from dataclasses import dataclass
from rag.chunking.types import Chunk
from rag.chunking.errors import ChunkTooLong
from rag.nlp.token_count import count_tokens
from rag.parsers.errors import NoReadableText


@dataclass(frozen=True)
class PictureConfig:
    pass


def chunk(blocks, cfg):
    for i, block in enumerate(blocks):
        if not block.text.strip() or not block.image_ids:
            raise NoReadableText()
        tokens = count_tokens(block.text)
        if tokens > 8191:
            raise ChunkTooLong()
        yield Chunk(block.text, block.boxes, block.page_sizes, tokens, i, image_ids=block.image_ids)
