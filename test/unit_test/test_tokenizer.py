"""Stdlib tokenizer and token counting (plan 04-06, D-27, CHUNK-17)."""

from __future__ import annotations

import time

import pytest

from rag.nlp.normalize import normalize
from rag.nlp.token_count import count_tokens, split_at_tokens, truncate_tokens
from rag.nlp.tokenizer import fine_grained_tokenize, tokenize

pytestmark = pytest.mark.unit


def test_normalize_folds_width_and_case():
    assert normalize("ＡＢＣ １２３") == "abc 123"


def test_urls_and_emails_are_dropped():
    tokens = tokenize("Visit https://x.io/a?b=1 or mail a@b.com now")
    joined = " ".join(tokens)
    assert "visit" in tokens and "now" in tokens
    for bad in ("x.io", "https", "a@b", "com", "b=1"):
        assert bad not in joined


def test_cjk_unigrams_and_adjacent_pairs_plus_latin():
    tokens = tokenize("深度学习 model")
    for expected in ("深", "度", "学", "习", "深度", "度学", "学习", "model"):
        assert expected in tokens


def test_fine_grained_splits_case_underscore_and_digits():
    assert fine_grained_tokenize("camelCaseName_v2") == ["camel", "case", "name", "v", "2"]


def test_empty_input():
    assert tokenize("") == [] and tokenize("   ") == [] and fine_grained_tokenize("") == []


def test_linear_time_on_one_megabyte():
    text = ("word " * 100) + ("a" * 5000) + "深度学习" * 50 + " http://x.y/" + "z" * 2000
    big = (text * (1_000_000 // len(text) + 1))[:1_000_000]
    start = time.perf_counter()
    tokenize(big)
    fine_grained_tokenize(big)
    assert time.perf_counter() - start < 1.0 * 5  # generous CI headroom; quadratic code would take minutes


def test_pathological_long_runs_are_fast():
    start = time.perf_counter()
    tokenize("a" * 1_000_000)
    tokenize("x@" * 200_000)
    tokenize("h" * 1_000_000 + "://")
    assert time.perf_counter() - start < 3.0


def test_count_matches_cl100k():
    assert count_tokens("hello world") == 2
    assert count_tokens("") == 0


def test_truncate_and_split_respect_the_limit():
    text = "The quick brown fox jumps over the lazy dog. " * 40 + "深度学习与向量检索。" * 20
    cut = truncate_tokens(text, 25)
    assert count_tokens(cut) <= 25 and text.startswith(cut)
    pieces = split_at_tokens(text, 30)
    assert "".join(pieces) == text
    assert all(count_tokens(p) <= 31 for p in pieces)
    assert truncate_tokens("short", 100) == "short"
