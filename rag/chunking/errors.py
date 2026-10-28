"""Bounded chunking refusals, without service-layer dependencies."""


class ChunkTooLong(Exception):
    code = "chunk_too_long"

    def __init__(self) -> None:
        super().__init__("the whole document exceeds the embedding context")
