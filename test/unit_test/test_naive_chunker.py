"""Naive chunker and the chunker factory (plan 04-06, D-15, CHUNK-01, CHUNK-02)."""

from __future__ import annotations

import time

import pytest

from common.ingest_codes import IMPLEMENTED_PARSERS, METHOD_ORDER
from rag.chunking import factory
from rag.chunking.factory import ChunkerUnavailable, get_chunker
from rag.chunking.naive import NaiveConfig, chunk
from rag.nlp.token_count import count_tokens
from rag.parsers.types import PageBox, ParsedBlock

pytestmark = pytest.mark.unit


def _blocks(*texts):
    return [ParsedBlock(t) for t in texts]


def test_chunks_stay_under_the_limit_and_cover_the_input():
    texts = [("alpha beta gamma delta epsilon zeta eta theta. " * 3).replace(". ", ".\n") for _ in range(3)]
    out = list(chunk(_blocks(*texts), NaiveConfig(chunk_token_num=20, delimiter="\n")))
    assert len(out) > 1
    assert all(c.token_num <= 20 and count_tokens(c.text) <= 20 for c in out)
    assert "".join(c.text for c in out) == "".join(texts)
    assert [c.index for c in out] == list(range(len(out)))


def test_overlap_repeats_the_tail_of_the_previous_chunk():
    text = "".join(f"sentence number {i} is here.\n" for i in range(30))
    out = list(chunk(_blocks(text), NaiveConfig(chunk_token_num=40, delimiter="\n", overlapped_percent=20)))
    assert len(out) > 2
    for prev, nxt in zip(out, out[1:]):
        tail = prev.text[-8:]
        assert tail.strip() and tail in nxt.text[:60]
    assert all(c.token_num <= 40 for c in out)


def test_oversize_unit_is_split_not_dropped():
    text = "word " * 300
    out = list(chunk(_blocks(text), NaiveConfig(chunk_token_num=50, delimiter="\n")))
    assert len(out) >= 6
    assert all(c.token_num <= 51 for c in out)
    assert "".join(c.text for c in out).split() == text.split()


def test_boxes_and_page_sizes_are_merged_in_order():
    b1 = ParsedBlock("one\n", boxes=(PageBox(0, 1, 2, 3, 4),), page_sizes={0: (600.0, 800.0)})
    b2 = ParsedBlock("two\n", boxes=(PageBox(1, 5, 6, 7, 8),), page_sizes={1: (601.0, 801.0)})
    (c,) = list(chunk([b1, b2], NaiveConfig(chunk_token_num=100, delimiter="\n")))
    assert [b.page for b in c.positions] == [0, 1]
    assert dict(c.page_sizes) == {0: (600.0, 800.0), 1: (601.0, 801.0)}


def test_metacharacter_delimiters_are_literal():
    text = "a.*(b.*(c.*(d"
    out = list(chunk(_blocks(text), NaiveConfig(chunk_token_num=3, delimiter=".*(")))
    assert out and "".join(c.text for c in out).replace("\n", "") == text


def test_long_delimiter_set_is_fast():
    delim = "".join(chr(0x21 + i) for i in range(64))
    start = time.perf_counter()
    list(chunk(_blocks("ab" * 100000), NaiveConfig(chunk_token_num=512, delimiter=delim)))
    assert time.perf_counter() - start < 10


def test_empty_input_yields_nothing():
    assert list(chunk([], NaiveConfig())) == []
    assert list(chunk(_blocks("  \n"), NaiveConfig())) == []


def test_factory_returns_naive_and_refuses_the_rest():
    assert callable(get_chunker("naive"))
    for method in ("qa", "paper", "book", "laws", "presentation", "table", "manual", "unknown", ""):
        with pytest.raises(ChunkerUnavailable) as info:
            get_chunker(method)
        assert info.value.code == "chunker_unavailable"


def test_methods_match_the_vocabulary():
    assert factory.METHODS == METHOD_ORDER
    assert {m for m in factory.METHODS if not factory.available(m)} == set(METHOD_ORDER) - IMPLEMENTED_PARSERS
