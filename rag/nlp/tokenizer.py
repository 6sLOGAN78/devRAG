"""Latin words and normalized Chinese dictionary terms with source offsets (D-27, Phase6-12)."""

from __future__ import annotations

import re

from rag.nlp.normalize import nfkc, normalize, strip_links

_CJK = "一-鿿㐀-䶿぀-ヿ가-힯"
_TOKEN = re.compile(rf"([{_CJK}]+)|((?:(?![{_CJK}])[^\W_])+)")
_CJK_START = re.compile(rf"[{_CJK}]")
_FINE = re.compile(rf"[{_CJK}]+|[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+|[^\W\d_]+")


def has_chinese(text: str) -> bool:
    return bool(re.search(r"[一-鿿㐀-䶿]", text))


def tokenize(text: str) -> list[str]:
    if has_chinese(text):
        return [span.text for span in tokenize_with_offsets(text)]
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
    if re.search(r"[一-鿿㐀-䶿]", text):
        from rag.nlp.chinese import simplify

        text = re.sub(r"[一-鿿㐀-䶿]{1,128}", lambda m: simplify(m[0]), text)
    out: list[str] = []
    for piece in _FINE.findall(strip_links(nfkc(text))):
        if _CJK_START.match(piece):
            out.extend(piece)
        else:
            out.append(piece.lower())
    return out


def tokenize_with_offsets(text: str):
    from rag.nlp.token_offsets import normalized_source, TokenSpan
    from rag.nlp.chinese import words

    value, offsets = normalized_source(text)
    result = []

    def add(token, start, end):
        result.append(TokenSpan(token, offsets[start][0], offsets[end - 1][1]))

    for match in _TOKEN.finditer(value):
        cjk, word = match.groups()
        start = match.start()
        if word:
            add(word, start, match.end())
        else:
            for i, char in enumerate(cjk):
                add(char, start + i, start + i + 1)
            for i in range(len(cjk) - 1):
                add(cjk[i : i + 2], start + i, start + i + 2)
            # Add longer dictionary words; existing unigram/bigram recall and order remain.
            for base in range(0, len(cjk), 128):
                for token, a, b in words(cjk[base : base + 128]):
                    if len(token) > 2:
                        add(token, start + base + a, start + base + b)
    return result
