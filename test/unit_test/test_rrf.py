"""Reciprocal rank fusion with k = 60 (RETR-07)."""

from __future__ import annotations

from fractions import Fraction

import pytest

from rag.nlp.fusion import rrf

pytestmark = pytest.mark.unit


def test_rrf_fixed_fractions_for_two_rankings() -> None:
    out = rrf([["a", "b", "c"], ["b", "c", "a"]])
    # ranks of a: (1, 3); b: (2, 1); c: (3, 2)
    assert out["a"] == pytest.approx(float(Fraction(1, 61) + Fraction(1, 63)), abs=1e-12)
    assert out["b"] == pytest.approx(float(Fraction(1, 62) + Fraction(1, 61)), abs=1e-12)
    assert out["c"] == pytest.approx(float(Fraction(1, 63) + Fraction(1, 62)), abs=1e-12)


def test_rrf_second_ranking_as_stated_in_the_plan() -> None:
    # ranks (1,2,3) and (3,1,2) of ids a, b, c
    out = rrf([["a", "b", "c"], ["b", "c", "a"]])
    assert out["a"] == pytest.approx(1 / 61 + 1 / 63, abs=1e-12)
    assert out["b"] == pytest.approx(1 / 62 + 1 / 61, abs=1e-12)
    assert out["c"] == pytest.approx(1 / 63 + 1 / 62, abs=1e-12)
    assert max(out, key=out.__getitem__) == "b"


def test_rrf_single_ranking_and_custom_k() -> None:
    assert rrf([["x", "y"]]) == {"x": pytest.approx(1 / 61), "y": pytest.approx(1 / 62)}
    assert rrf([["x"]], k=10) == {"x": pytest.approx(1 / 11)}


def test_rrf_empty() -> None:
    assert rrf([]) == {}
    assert rrf([[], []]) == {}


def test_rrf_id_missing_from_a_ranking_gets_nothing_from_it() -> None:
    out = rrf([["a"], ["b"]])
    assert out["a"] == pytest.approx(1 / 61) and out["b"] == pytest.approx(1 / 61)
