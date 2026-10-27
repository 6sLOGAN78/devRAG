"""Canonical citation markers and deterministic embedding fallback (plan 05-10)."""
from __future__ import annotations

import math

import pytest

from rag.prompts.citations import canonicalise, insert_citations, strip_markers, valid_indices

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("raw", "count", "wanted"),
    [
        ("one ##0$$", 1, "one ##0$$"),
        ("one ## 0 $$", 1, "one ##0$$"),
        ("one ##0 $$", 1, "one ##0$$"),
        ("one ## 0$$", 1, "one ##0$$"),
        ("one [ID:0]", 1, "one ##0$$"),
        ("one [ID: 0]", 1, "one ##0$$"),
        ("one [0]", 1, "one ##0$$"),
        ("one [2]", 3, "one ##2$$"),
        ("one [2]", 2, "one [2]"),
        ("one (3)", 4, "one (3)"),
        ("one ##3$$", 3, "one "),
        ("one ## 3 $$", 3, "one "),
        ("one [ID:3]", 3, "one "),
        ("one ##1$$##1$$", 2, "one ##1$$"),
        ("one ##0$$##2$$", 3, "one ##0$$##2$$"),
        ("事实[ID:1]。", 2, "事实##1$$。"),
        ("`code [ID:0]` prose [ID:0]", 1, "`code [ID:0]` prose ##0$$"),
        ("```\n[ID:0]\n``` prose [0]", 1, "```\n[ID:0]\n``` prose ##0$$"),
        ("````\n[0]\n````", 1, "````\n[0]\n````"),
        ("no citation", 0, "no citation"),
        ("mixed [1] and ##0$$", 1, "mixed [1] and ##0$$"),
        ("##01$$", 2, "##1$$"),
    ],
)
def test_canonicalise_variants(raw, count, wanted):
    assert canonicalise(raw, count) == wanted


def test_valid_indices_are_distinct_in_first_seen_order_and_ignore_code():
    assert valid_indices("##2$$ ##0$$ ##2$$ `##1$$` ##9$$", 3) == [2, 0]


def test_strip_markers_removes_all_and_collapses_double_spaces():
    assert strip_markers("first ##0$$  second ##12$$") == "first second "


def _embed(texts):
    return [[1.0, 0.0, 0.0] if "alpha" in text else [0.0, 1.0, 0.0] for text in texts]


def test_fallback_cites_each_matching_sentence():
    result = insert_citations("alpha fact. beta fact!", {0: [1, 0, 0], 1: [0, 1, 0]}, _embed)
    assert result.inserted and result.text == "alpha fact.##0$$ beta fact!##1$$"


def test_fallback_uses_first_threshold_with_any_match():
    medium = [0.5, math.sqrt(0.75), 0]
    result = insert_citations("alpha fact.", {0: medium}, _embed)
    assert result.inserted and result.text == "alpha fact.##0$$"


def test_fallback_skips_code_and_cites_prose():
    result = insert_citations("```\nalpha code\n```\nalpha fact.", {0: [1, 0, 0]}, _embed)
    assert result.inserted and "alpha code\n```" in result.text and result.text.endswith("alpha fact.##0$$")


def test_fallback_does_not_embed_when_a_valid_marker_exists():
    calls = []
    result = insert_citations("already cited ##0$$", {0: [1, 0, 0]}, lambda texts: calls.append(texts) or _embed(texts))
    assert not result.inserted and result.text == "already cited ##0$$" and calls == []


def test_fallback_no_match_returns_original():
    result = insert_citations("alpha fact.", {0: [0, 0, 1]}, _embed)
    assert not result.inserted and result.text == "alpha fact."


@pytest.mark.parametrize("vectors", [{}, {0: [0, 0, 0]}, {0: []}])
def test_fallback_zero_or_missing_vectors_is_safe(vectors):
    result = insert_citations("alpha fact.", vectors, _embed)
    assert result.text == "alpha fact." and not result.inserted


def test_fallback_caps_two_citations_per_sentence():
    result = insert_citations("alpha fact.", {0: [1, 0, 0], 1: [1, 0, 0], 2: [1, 0, 0]}, _embed)
    assert result.inserted and result.text.count("##") == 2


def test_fallback_empty_answer_does_not_embed():
    result = insert_citations("   ", {0: [1, 0, 0]}, lambda _: pytest.fail("embed should not run"))
    assert not result.inserted and result.text == "   "
