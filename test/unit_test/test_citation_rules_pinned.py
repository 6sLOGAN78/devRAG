"""Changing citation instructions requires repeating the live adherence probe."""
from __future__ import annotations

import hashlib

import pytest

from rag.prompts.generator import CITATION_RULES

pytestmark = pytest.mark.unit
PINNED_SHA256 = "de84e758fc405a78d1b83c00dfa5f85dfa27d651c2c206c8c04ce2b5ffb714b6"


def test_citation_rules_digest_is_pinned_to_live_probe() -> None:
    assert hashlib.sha256(CITATION_RULES.encode()).hexdigest() == PINNED_SHA256, "rerun plan 05-13 citation adherence before changing rules"
