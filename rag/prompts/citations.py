"""Canonical citation markers and a sentence-embedding fallback (plan 05-10)."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

# The one marker definition shared by normalisation, validation and history stripping.
MARKER = re.compile(r"##(\d+)\$\$")


@dataclass(frozen=True)
class InsertResult:
    text: str
    inserted: bool


def _segments(text: str) -> list[tuple[bool, str]]:
    """Split prose from inline and fenced code without rewriting either kind of code."""
    parts: list[tuple[bool, str]] = []
    start = 0
    while start < len(text):
        tick = text.find("`", start)
        if tick < 0:
            parts.append((False, text[start:]))
            break
        if tick > start:
            parts.append((False, text[start:tick]))
        width = 1
        while tick + width < len(text) and text[tick + width] == "`":
            width += 1
        delimiter = "`" * width
        end = text.find(delimiter, tick + width)
        if end < 0:
            parts.append((True, text[tick:]))
            break
        finish = end + width
        parts.append((True, text[tick:finish]))
        start = finish
    return parts


def canonicalise(text: str, chunk_count: int) -> str:
    """Normalise model variants and drop impossible markers outside code."""
    count = max(0, chunk_count)

    def normalise_prose(prose: str) -> str:
        def marker(match: re.Match[str]) -> str:
            number = int(match.group(1))
            return f"##{number}$$" if number < count else ""

        def bracket(match: re.Match[str]) -> str:
            number = int(match.group(2))
            if number < count:
                return f"##{number}$$"
            return "" if match.group(1) else match.group(0)

        prose = re.sub(r"##\s*(\d+)\s*\$\$", marker, prose)
        prose = re.sub(r"\[(ID:\s*)?(\d+)\]", bracket, prose, flags=re.I)
        return re.sub(r"(##\d+\$\$)(?:\1)+", r"\1", prose)

    return "".join(part if code else normalise_prose(part) for code, part in _segments(text))


def valid_indices(text: str, chunk_count: int) -> list[int]:
    """Distinct, in-range cited indices in first-appearance order, ignoring code."""
    seen: set[int] = set()
    result: list[int] = []
    for code, part in _segments(text):
        if code:
            continue
        for match in MARKER.finditer(part):
            number = int(match.group(1))
            if 0 <= number < chunk_count and number not in seen:
                seen.add(number)
                result.append(number)
    return result


def strip_markers(text: str) -> str:
    """Remove every canonical marker from prior assistant text before reuse as history."""
    return re.sub(r" {2,}", " ", MARKER.sub("", text))


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or len(left) != len(right):
        return -1.0
    a = math.sqrt(sum(value * value for value in left))
    b = math.sqrt(sum(value * value for value in right))
    if a == 0 or b == 0:
        return -1.0
    return sum(x * y for x, y in zip(left, right, strict=True)) / (a * b)


def insert_citations(
    answer: str,
    chunk_vectors: Mapping[int, Sequence[float]],
    embed: Callable[[list[str]], list[list[float]]],
    *,
    thresholds: tuple[float, ...] = (0.63, 0.53, 0.43, 0.33, 0.3),
    max_per_sentence: int = 2,
) -> InsertResult:
    """Embed uncited prose once; cite each sentence at the first threshold with any match."""
    original = InsertResult(answer, False)
    if not answer.strip() or not chunk_vectors or max_per_sentence < 1:
        return original
    if valid_indices(answer, max(chunk_vectors) + 1):
        return original

    segments = _segments(answer)
    sentences: list[tuple[int, int, int, str]] = []
    for segment_index, (code, part) in enumerate(segments):
        if code:
            continue
        for match in re.finditer(r"[^.!?。！？\n]+[.!?。！？]*|\n", part):
            candidate = match.group(0).strip()
            if candidate:
                sentences.append((segment_index, match.start(), match.end(), candidate))
    if not sentences:
        return original
    vectors = embed([candidate for _, _, _, candidate in sentences])
    if len(vectors) != len(sentences):
        return original
    ranked = [
        sorted(((index, _cosine(vector, chunk)) for index, chunk in chunk_vectors.items()), key=lambda item: (-item[1], item[0]))
        for vector in vectors
    ]
    threshold = next((cutoff for cutoff in thresholds if any(scores and scores[0][1] >= cutoff for scores in ranked)), None)
    if threshold is None:
        return original

    inserts: dict[int, list[tuple[int, str]]] = {}
    for (segment_index, _, end, _), scores in zip(sentences, ranked, strict=True):
        chosen = [index for index, score in scores if score >= threshold][:max_per_sentence]
        if chosen:
            inserts.setdefault(segment_index, []).append((end, "".join(f"##{index}$$" for index in chosen)))
    if not inserts:
        return original
    out: list[str] = []
    for segment_index, (_, part) in enumerate(segments):
        for position, markers in reversed(inserts.get(segment_index, [])):
            part = part[:position] + markers + part[position:]
        out.append(part)
    return InsertResult("".join(out), True)
