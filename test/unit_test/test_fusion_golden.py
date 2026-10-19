"""Golden numbers for the hybrid score (RETR-06, RETR-13, RETR-14, RETR-15; R-195).

The weight is the vector share: score = (1 - w) * term + w * vector + rank_feature. A build that uses the vector weight
for the term share turns these tests red.
"""

from __future__ import annotations

import math

import pytest

from rag.nlp.fusion import apply_threshold, cosine_from_es_score, fuse, paginate, rank_feature, token_overlap

pytestmark = pytest.mark.unit

A = (1.0, 0.2)  # strong on terms, weak on meaning
B = (0.2, 1.0)  # weak on terms, strong on meaning


def _rank(weight: float) -> list[str]:
    scored = [("A", fuse(A[0], A[1], weight)), ("B", fuse(B[0], B[1], weight))]
    return [name for name, _ in sorted(scored, key=lambda p: p[1], reverse=True)]


def test_golden_numbers_at_weight_point_three() -> None:
    assert fuse(*A, 0.3) == pytest.approx(0.76, abs=1e-9)
    assert fuse(*B, 0.3) == pytest.approx(0.44, abs=1e-9)
    assert _rank(0.3) == ["A", "B"]


def test_weight_zero_puts_the_term_match_first_and_weight_one_the_vector_match() -> None:
    assert _rank(0.0) == ["A", "B"]
    assert _rank(1.0) == ["B", "A"]
    assert fuse(*A, 0.0) == pytest.approx(1.0)
    assert fuse(*B, 1.0) == pytest.approx(1.0)


def _swapped(tsim: float, vsim: float, w: float) -> float:
    return w * tsim + (1 - w) * vsim


def test_swapped_weights_do_not_match_the_golden_numbers() -> None:
    assert _swapped(*A, 0.3) == pytest.approx(0.44, abs=1e-9)
    assert _swapped(*B, 0.3) == pytest.approx(0.76, abs=1e-9)
    assert fuse(*A, 0.3) != pytest.approx(_swapped(*A, 0.3), abs=1e-6)
    assert fuse(*B, 0.3) != pytest.approx(_swapped(*B, 0.3), abs=1e-6)


def test_rank_feature_is_added_after_the_weighted_share() -> None:
    assert fuse(*A, 0.3, rank_fea=0.5) == pytest.approx(1.26, abs=1e-9)


@pytest.mark.parametrize("bad", [-0.01, 1.01, float("nan")])
def test_weight_outside_zero_one_is_refused(bad: float) -> None:
    with pytest.raises(ValueError):
        fuse(0.5, 0.5, bad)


@pytest.mark.parametrize(
    ("score", "expected"),
    [(1.0, 1.0), (0.75, 0.5), (0.5, 0.0), (0.0, 0.0), (2.0, 1.0), (1.5, 1.0)],
)
def test_cosine_from_es_score_clamps(score: float, expected: float) -> None:
    assert cosine_from_es_score(score) == pytest.approx(expected)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_cosine_from_es_score_non_finite_is_zero(bad: float) -> None:
    assert cosine_from_es_score(bad) == 0.0


def test_token_overlap() -> None:
    assert token_overlap(["a", "b", "c", "d"], ["a", "c", "x"]) == pytest.approx(0.5)
    assert token_overlap(["a", "a", "b"], ["a"]) == pytest.approx(0.5)
    assert token_overlap([], ["a"]) == 0.0
    assert token_overlap(["a"], []) == 0.0


def test_rank_feature() -> None:
    assert rank_feature(0.5, 2.0) == pytest.approx(7.0)
    assert rank_feature(None, None) == 0.0
    assert rank_feature(None, 3.0) == 3.0
    assert rank_feature(0.1, None) == pytest.approx(1.0)


def test_threshold_drops_below_and_keeps_equal_with_stable_order() -> None:
    scored = [("a", 0.5), ("b", 0.19), ("c", 0.5), ("d", 0.2), ("e", 0.9)]
    out = apply_threshold(scored, 0.2)
    assert [name for name, _ in out] == ["e", "a", "c", "d"]


def test_threshold_default_is_not_hidden() -> None:
    assert apply_threshold([("a", 0.2)], 0.2) == [("a", 0.2)]
    assert apply_threshold([("a", 0.1999)], 0.2) == []


def test_threshold_ignores_nan_scores() -> None:
    assert apply_threshold([("a", math.nan), ("b", 0.4)], 0.2) == [("b", 0.4)]


def test_paginate_slices_a_window_and_reports_total() -> None:
    items = list(range(25))
    page, total = paginate(items, 2, 10)
    assert page == list(range(10, 20))
    assert total == 25
    last, _ = paginate(items, 3, 10)
    assert last == [20, 21, 22, 23, 24]
    beyond, total2 = paginate(items, 9, 10)
    assert beyond == [] and total2 == 25


@pytest.mark.parametrize(("page", "size"), [(0, 10), (1, 0), (-1, 5)])
def test_paginate_refuses_non_positive_page_or_size(page: int, size: int) -> None:
    with pytest.raises(ValueError):
        paginate([1, 2, 3], page, size)
