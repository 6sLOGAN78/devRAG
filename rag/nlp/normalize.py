"""Text normalisation for tokenising: NFKC (full-width to half-width), lower case, whitespace collapse.

Chinese dictionary conversion and source offsets are handled separately by token_offsets/chinese.
"""

from __future__ import annotations

import re
import unicodedata

_SPACES = re.compile(r"\s+")


def nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def normalize(text: str) -> str:
    return _SPACES.sub(" ", nfkc(text).lower()).strip()


def _is_link(word: str) -> bool:
    if "://" in word or word.startswith("www."):
        return True
    local, at, domain = word.partition("@")
    return bool(at and local and "." in domain.strip(".") and not domain.startswith("."))


def strip_links(text: str) -> str:
    """Drop URLs and e-mail addresses word by word (split on whitespace, so no backtracking pattern is needed)."""
    return " ".join(w for w in text.split() if not _is_link(w))
