"""Academic sections from explicit headings and whole-line scientific section labels."""

from dataclasses import dataclass, replace
import re

from rag.chunking.errors import ChunkTooLong
from rag.chunking.types import Chunk
from rag.nlp.token_count import count_tokens, split_at_tokens
from rag.parsers.sections import Section

_NUMBER = re.compile(r"^(\d+(?:\.\d+)*)(?:\.)?\s+(.+)$")
_LABELS = frozenset({"abstract", "introduction", "background", "related work", "methods", "methodology", "materials and methods", "measurements", "experiments", "results", "discussion", "conclusion", "conclusions", "references", "bibliography", "acknowledgements", "摘要", "引言", "背景", "相关工作", "方法", "实验", "结果", "讨论", "结论", "参考文献"})


@dataclass(frozen=True)
class PaperConfig:
    chunk_token_num: int = 512


def _heading(block):
    if block.kind not in {"text", "heading"}:
        return None
    text = block.text.strip()
    if block.kind == "heading":
        text = re.sub(r"\n[=-]+\s*$", "", text)
        text = re.sub(r"^#{1,6}\s+", "", text).strip()
    match = _NUMBER.fullmatch(text)
    label = match[2] if match else text
    if block.kind != "heading" and ("\n" in text or label.casefold() not in _LABELS):
        return None
    if not text or len(text) > 1024:
        raise ChunkTooLong()
    level = len(match[1].split(".")) if match else (block.heading_level or 1)
    return text, min(level, 6)


def _lines(blocks):
    for block in blocks:
        # PDF text runs may contain a heading and body in the same block.
        if block.kind == "text" and "\n" in block.text:
            for line in block.text.splitlines():
                if line.strip():
                    yield replace(block, text=line)
        else:
            yield block


def chunk(blocks, cfg: PaperConfig):
    yield from section_chunks(_lines(blocks), cfg, _heading)


def section_chunks(blocks, cfg, heading_of):
    """Shared bounded emission; each domain supplies its own heading recognition."""
    ancestry = []
    group = []
    index = 0

    def emit(items, parents):
        nonlocal index
        if not items:
            return
        labels = tuple(title for title, _ in parents)
        prefix = "\n".join(labels)
        prefix = prefix + "\n" if prefix else ""
        body = "\n".join(b.text for b in items if heading_of(b) is None)
        limit = max(1, min(cfg.chunk_token_num, 8191))
        budget = limit - count_tokens(prefix)
        if budget < 1:
            raise ChunkTooLong()
        pieces = split_at_tokens(body, budget) if body else [""]
        while budget > 1 and any(count_tokens(prefix + part) > limit for part in pieces):
            budget -= 1
            pieces = split_at_tokens(body, budget)
        for part in pieces:
            text = prefix + part
            if not text.strip():
                continue
            tokens = count_tokens(text)
            if tokens > limit:
                raise ChunkTooLong()
            yield Chunk(text, tuple(box for b in items for box in b.boxes),
                        {p: size for b in items for p, size in b.page_sizes.items()}, tokens, index,
                        tables=tuple(b.table for b in items if b.table is not None),
                        image_ids=tuple(dict.fromkeys(i for b in items for i in b.image_ids)),
                        source_lines=tuple(dict.fromkeys(b.line_range for b in items if b.line_range is not None)),
                        sections=(Section(labels),))
            index += 1

    for block in blocks:
        heading = heading_of(block)
        if heading:
            if any(heading_of(b) is None for b in group):
                yield from emit(group, ancestry)
                group = []
            title, level = heading
            ancestry = [parent for parent in ancestry if parent[1] < level]
            ancestry.append((title, level))
        group.append(block)
    yield from emit(group, ancestry)
