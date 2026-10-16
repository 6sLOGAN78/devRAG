"""Token counting with the shared cl100k_base encoding (no download, see ``rag.llm.embedding_model``)."""

from __future__ import annotations

from rag.llm.embedding_model import cl100k_encoding


def _tokens(text: str) -> list[int]:
    return cl100k_encoding().encode(text, disallowed_special=())


def count_tokens(text: str) -> int:
    return len(_tokens(text)) if text else 0


def _offsets(text: str, tokens: list[int]) -> list[int]:
    _, offsets = cl100k_encoding().decode_with_offsets(tokens)
    return offsets


def split_at_tokens(text: str, limit: int) -> list[str]:
    """Cut ``text`` into consecutive pieces of at most ``limit`` tokens; joining the pieces returns ``text``."""
    if limit < 1:
        raise ValueError("limit must be positive")
    if not text:
        return []
    tokens = _tokens(text)
    if len(tokens) <= limit:
        return [text]
    offsets = _offsets(text, tokens)
    cuts = [offsets[i] for i in range(0, len(tokens), limit)] + [len(text)]
    pieces = [text[a:b] for a, b in zip(cuts, cuts[1:], strict=False) if b > a]
    return pieces


def truncate_tokens(text: str, limit: int) -> str:
    """The first ``limit`` tokens of ``text`` as text."""
    pieces = split_at_tokens(text, limit)
    return pieces[0] if pieces else ""


def tail_tokens(text: str, count: int) -> str:
    """The last ``count`` tokens of ``text`` as text."""
    if count < 1 or not text:
        return ""
    tokens = _tokens(text)
    if len(tokens) <= count:
        return text
    offsets = _offsets(text, tokens)
    return text[offsets[len(tokens) - count] :]
