"""Stdlib tokenizer (D-27): Latin by word, CJK as unigrams plus adjacent pairs, URLs and e-mail addresses removed."""

from __future__ import annotations

import re

from rag.nlp.normalize import nfkc, normalize, strip_links

_CJK = "一-鿿㐀-䶿぀-ヿ가-힯"
_TOKEN = re.compile(rf"([{_CJK}]+)|((?:(?![{_CJK}])[^\W_])+)")
_CJK_START = re.compile(rf"[{_CJK}]")
_FINE = re.compile(rf"[{_CJK}]+|[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+|[^\W\d_]+")


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for cjk, word in _TOKEN.findall(normalize(strip_links(nfkc(text)))):
        if word:
            tokens.append(word)
        elif cjk:
            tokens.extend(cjk)
            tokens.extend(cjk[i : i + 2] for i in range(len(cjk) - 1))
    return tokens


def fine_grained_tokenize(text: str) -> list[str]:
    """Split on case, underscore and digit boundaries; CJK runs are split into single characters."""
    out: list[str] = []
    for piece in _FINE.findall(strip_links(nfkc(text))):
        if _CJK_START.match(piece):
            out.extend(piece)
        else:
            out.append(piece.lower())
    return out
