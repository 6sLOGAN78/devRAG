"""One bounded timestamped speech segment per chunk, without PDF geometry."""

from dataclasses import dataclass
from rag.chunking.types import Chunk
from rag.chunking.errors import ChunkTooLong
from rag.parsers.errors import NoReadableText
from rag.nlp.token_count import count_tokens


@dataclass(frozen=True)
class AudioConfig:
    pass


def chunk(blocks, cfg):
    previous = 0
    for i, block in enumerate(blocks):
        if block.audio is None or block.audio.start < previous or block.boxes or not block.text.strip():
            raise NoReadableText()
        previous = block.audio.end
        tokens = count_tokens(block.text)
        if tokens > 8191:
            raise ChunkTooLong()
        yield Chunk(block.text, (), {}, tokens, i, audio=block.audio)
