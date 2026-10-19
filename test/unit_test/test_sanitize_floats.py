"""NaN and Infinity become null before serialisation (RETR-19)."""

from __future__ import annotations

import json
import math

import pytest

from rag.nlp.fusion import sanitize_floats

pytestmark = pytest.mark.unit


def test_non_finite_floats_become_none_in_nested_structures() -> None:
    obj = {"a": math.nan, "b": [1, math.inf, {"c": -math.inf, "d": 2.5}], "e": (math.nan, "x")}
    out = sanitize_floats(obj)
    assert out == {"a": None, "b": [1, None, {"c": None, "d": 2.5}], "e": (None, "x")}
    json.dumps(out, allow_nan=False)


def test_bare_non_finite_float() -> None:
    assert sanitize_floats(math.nan) is None
    assert sanitize_floats(math.inf) is None


def test_other_scalars_are_unchanged() -> None:
    for value in (0, 7, 1.5, "s", True, False, None, ""):
        out = sanitize_floats(value)
        assert out == value and type(out) is type(value)


def test_tuples_stay_tuples_and_inputs_are_not_mutated() -> None:
    src = {"t": (1, math.nan), "l": [math.inf]}
    out = sanitize_floats(src)
    assert isinstance(out["t"], tuple) and out["t"] == (1, None)
    assert math.isnan(src["t"][1]) and src["l"] == [math.inf]
