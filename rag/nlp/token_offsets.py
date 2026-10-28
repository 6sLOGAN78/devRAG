"""Normalized characters retain half-open source spans, including combining sequences."""

from dataclasses import dataclass
import re
import unicodedata

from rag.nlp.normalize import _is_link
from rag.nlp.chinese import simplify

_CJK = re.compile(r"[一-鿿㐀-䶿]+")


@dataclass(frozen=True)
class TokenSpan:
    text: str
    start: int
    end: int


def normalized_source(text: str):
    chars, spans = [], []
    for word in re.finditer(r"\S+", text):
        raw = word.group()
        if _is_link(unicodedata.normalize("NFKC", raw)):
            continue
        if chars:
            chars.append(" ")
            spans.append((word.start(), word.start()))
        start = 0
        while start < len(raw):
            end = start + 1
            while end < len(raw) and unicodedata.combining(raw[end]):
                end += 1
            normalized = unicodedata.normalize("NFKC", raw[start:end]).lower()
            chars.extend(normalized)
            spans.extend([(word.start() + start, word.start() + end)] * len(normalized))
            start = end
    value = "".join(chars)
    out, positions, previous = [], [], 0
    for match in _CJK.finditer(value):
        out.append(value[previous : match.start()])
        positions.extend(spans[previous : match.start()])
        # Bound dictionary recursion/work on pathological unpunctuated CJK runs.
        for start in range(match.start(), match.end(), 128):
            end = min(start + 128, match.end())
            converted = simplify(value[start:end])
            out.append(converted)
            positions.extend(spans[start:end] if len(converted) == end - start else [(spans[start][0], spans[end - 1][1])] * len(converted))
        previous = match.end()
    out.append(value[previous:])
    positions.extend(spans[previous:])
    return "".join(out), positions
