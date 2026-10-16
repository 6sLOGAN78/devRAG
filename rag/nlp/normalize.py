"""Text normalisation for tokenising: NFKC (full-width to half-width), lower case, whitespace collapse.

Traditional-to-simplified Chinese conversion is NOT performed (D-27, R-160): it needs a mapping table that is not in the
approved package set. CHUNK-17 is therefore recorded as partial. Every function here runs in linear time.
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
