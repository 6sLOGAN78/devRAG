"""Résumé sections with exact source spans, explicit model inference and no invented fields."""
from collections.abc import Callable
from dataclasses import dataclass
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError
from rag.chunking.errors import ChunkTooLong
from rag.chunking.types import Chunk
from rag.nlp.token_count import count_tokens, split_at_tokens
from rag.parsers.errors import FileDamaged, FileTooLarge, NoReadableText
from rag.parsers.sections import Section

LABELS = {"name": ("Resume", "Name"), "email": ("Resume", "Contact", "Email"), "phone": ("Resume", "Contact", "Phone"), "work": ("Resume", "Work History"), "education": ("Resume", "Education"), "skills": ("Resume", "Skills")}
HEADINGS = {"name":"name", "email":"email", "phone":"phone", "work history":"work", "work experience":"work", "experience":"work", "education":"education", "skills":"skills", "姓名":"name", "邮箱":"email", "电话":"phone", "工作经历":"work", "教育经历":"education", "技能":"skills"}
_MISSING = frozenset({"unknown", "not provided", "not available", "n/a", "none", "未知", "未提供"})
MAX_INPUT_CHARS = 16384
MAX_INPUT_TOKENS = 6000


class SourceSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: Literal["name", "email", "phone", "work", "education", "skills"]
    source: StrictInt = Field(ge=0, le=127)
    start: StrictInt = Field(ge=0, le=MAX_INPUT_CHARS)
    end: StrictInt = Field(ge=1, le=MAX_INPUT_CHARS)


class ResumeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sections: list[SourceSpan] = Field(min_length=1, max_length=64)


@dataclass(frozen=True)
class ResumeConfig:
    chunk_token_num: int = 512
    infer: Callable[[list[str]], str] | None = None


def bounded_sources(blocks):
    if len(blocks) > 128 or sum(len(b.text) for b in blocks) > MAX_INPUT_CHARS or sum(count_tokens(b.text) for b in blocks) > MAX_INPUT_TOKENS:
        raise FileTooLarge()
    return [b.text for b in blocks]


def _structured(blocks):
    spans = []
    field = None
    recognized = False
    for source, block in enumerate(blocks):
        offset = 0
        for line in block.text.splitlines(keepends=True):
            raw = line.strip()
            label, sep, value = raw.partition(":")
            heading = re.sub(r"^#{1,6}\s+", "", label).strip().casefold()
            selected = HEADINGS.get(heading)
            if selected:
                recognized = True
                field = selected
                raw = value.strip() if sep else ""
            elif raw and field is None:
                return None  # An unlabelled introduction needs explicit inference.
            if raw and field and raw.casefold() not in _MISSING:
                start = offset + line.index(raw)
                spans.append(SourceSpan(field=field, source=source, start=start, end=start + len(raw)))
            offset += len(line)
    return spans if recognized else None


def _validate(spans, blocks):
    if len(spans) > 64:
        raise FileTooLarge()
    seen = set()
    for span in spans:
        if span.source >= len(blocks) or span.start >= span.end or span.end > len(blocks[span.source].text):
            raise FileDamaged()
        value = blocks[span.source].text[span.start:span.end]
        key = (span.source, span.start, span.end)
        if key in seen or not value.strip() or "\0" in value:
            raise FileDamaged()
        seen.add(key)
        if span.field == "email" and not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", value):
            raise FileDamaged()
        if span.field == "phone" and (not re.fullmatch(r"\+?[0-9 ()-]{7,40}", value) or sum(c.isdigit() for c in value) < 7):
            raise FileDamaged()
        if span.field == "name" and (len(value) > 256 or "\n" in value or not any(c.isalpha() for c in value)):
            raise FileDamaged()
    return sorted(spans, key=lambda s: (s.source, s.start, s.end))


def chunk(blocks, cfg):
    blocks = list(blocks)
    texts = bounded_sources(blocks)
    spans = _structured(blocks)
    if spans is None:
        if cfg.infer is None:
            raise NoReadableText()
        response = cfg.infer(texts)  # Exactly one call, no repair/fallback loop.
        if not isinstance(response, str) or len(response) > 65536:
            raise FileDamaged()
        try:
            spans = ResumeResponse.model_validate_json(response).sections
        except (ValidationError, ValueError, TypeError):
            raise FileDamaged() from None
    if not spans:
        raise NoReadableText()
    spans = _validate(spans, blocks)
    index = 0
    for span in spans:
        block = blocks[span.source]
        value = block.text[span.start:span.end]
        label = LABELS[span.field]
        prefix = " / ".join(label) + "\n"
        target = min(cfg.chunk_token_num, 8191)
        budget = target - count_tokens(prefix)
        if budget < 1:
            raise ChunkTooLong()
        pieces = split_at_tokens(value, budget)
        while budget > 1 and any(count_tokens(prefix + piece) > target for piece in pieces):
            budget -= 1
            pieces = split_at_tokens(value, budget)
        for piece in pieces:
            text = prefix + piece
            tokens = count_tokens(text)
            if tokens > target:
                raise ChunkTooLong()
            yield Chunk(text, block.boxes, block.page_sizes, tokens, index,
                        image_ids=block.image_ids,
                        source_lines=(block.line_range,) if block.line_range else (),
                        sections=(Section(label),))
            index += 1
