"""One validated Q&A pair per chunk; preserve source and never fall back or split."""

from __future__ import annotations

import re
from dataclasses import dataclass

from rag.chunking.errors import ChunkTooLong, InvalidPair
from rag.chunking.types import Chunk
from rag.nlp.token_count import count_tokens
from rag.parsers.records import MAX_RECORDS, scalar_text

QUESTIONS = {"question", "q", "问题"}
ANSWERS = {"answer", "a", "答案"}
_MARKER = re.compile(r"^(Question|Q|Answer|A|问题|答案)[ \t]*[:：][ \t]?(.*)$", re.IGNORECASE)


@dataclass(frozen=True)
class QAConfig:
    max_tokens: int = 8191


def _record_pair(record):
    questions = [f for f in record.fields if f.name.strip().casefold() in QUESTIONS]
    answers = [f for f in record.fields if f.name.strip().casefold() in ANSWERS]
    if len(questions) != 1 or len(answers) != 1:
        raise InvalidPair()
    q, a = questions[0], answers[0]
    if q.path.rsplit("/", 1)[0] != a.path.rsplit("/", 1)[0] or not isinstance(q.value, str) or not q.value.strip() or a.value is None or not scalar_text(a.value).strip():
        raise InvalidPair()
    return q.value


def _text_pairs(blocks):
    text = "\n\n".join(b.text for b in blocks)
    if len(text.encode()) > 100 * 1024 * 1024:
        raise ChunkTooLong()
    source, question, answer = [], [], None
    count = 0
    for line in text.splitlines(keepends=True):
        match = _MARKER.fullmatch(line.rstrip("\r\n"))
        if match and match[1].casefold() in QUESTIONS:
            if source:
                if not question or answer is None or not "".join(answer).strip():
                    raise InvalidPair()
                yield "".join(source), "".join(question).strip()
                count += 1
                if count >= MAX_RECORDS:
                    raise InvalidPair()
            source, question, answer = [line], [match[2] + "\n"], None
        elif match:
            if not source or answer is not None or not "".join(question).strip():
                raise InvalidPair()
            source.append(line)
            answer = [match[2] + "\n"]
        elif not source:
            if line.strip():
                raise InvalidPair()
        else:
            source.append(line)
            (question if answer is None else answer).append(line)
    if not source or not "".join(question).strip() or answer is None or not "".join(answer).strip():
        raise InvalidPair()
    yield "".join(source), "".join(question).strip()


def chunk(blocks, cfg: QAConfig):
    blocks = list(blocks)
    if not blocks:
        raise InvalidPair()
    if any(block.record is not None for block in blocks):
        if any(block.record is None for block in blocks):
            raise InvalidPair()
        pairs = [(block.text, _record_pair(block.record), [block]) for block in blocks]
    else:
        pairs = [(text, question, blocks) for text, question in _text_pairs(blocks)]
    for index, (text, question, source) in enumerate(pairs):
        tokens = count_tokens(text)
        if tokens > cfg.max_tokens:
            raise ChunkTooLong()
        yield Chunk(
            text,
            tuple(box for block in source for box in block.boxes),
            {p: s for block in source for p, s in block.page_sizes.items()},
            tokens,
            index,
            tables=tuple(block.table for block in source if block.table is not None),
            image_ids=tuple(dict.fromkeys(i for block in source for i in block.image_ids)),
            source_lines=tuple(block.line_range for block in source if block.line_range is not None),
            question=question,
        )
