"""Pure citation adherence classification and the pre-agreed model switch rule."""
from __future__ import annotations

import pytest

from scripts.probe.citation_adherence import Result, classify, decide, summarise

pytestmark = pytest.mark.unit
TOKEN = "Zorblax-4417"
CHUNKS = [{"index": 0, "content": "A different source"}, {"index": 2, "content": "Zorblax-4417 runs at 612 degrees"}]


def test_valid_marker_to_planted_chunk_with_answer_fact() -> None:
    result = classify("The coolant is 612 degrees ##2$$", CHUNKS, TOKEN, keywords=("612",))
    assert result.valid_markers == (2,) and result.cites_planted and not result.no_marker


def test_marker_to_another_chunk_does_not_count() -> None:
    result = classify("The coolant is 612 degrees ##0$$", CHUNKS, TOKEN, keywords=("612",))
    assert result.valid_markers == (0,) and not result.cites_planted


def test_marker_without_the_answer_fact_does_not_count() -> None:
    assert not classify("The coolant is unknown ##2$$", CHUNKS, TOKEN, keywords=("612",)).cites_planted


def test_no_marker_counts_as_no_marker() -> None:
    result = classify("The coolant is 612 degrees", CHUNKS, TOKEN, keywords=("612",))
    assert result.valid_markers == () and result.no_marker and not result.cites_planted


def test_out_of_range_marker_is_ignored() -> None:
    result = classify("The coolant is 612 degrees ##9$$", CHUNKS, TOKEN, keywords=("612",))
    assert result.valid_markers == () and result.no_marker


def test_fallback_insertion_is_counted_as_raw_no_marker_and_repair() -> None:
    result = classify("The coolant is 612 degrees ##2$$", CHUNKS, TOKEN, keywords=("612",), usage={"citations": "inserted"})
    assert result.cites_planted and result.no_marker and result.fallback_inserted


def test_summary_counts_all_dimensions() -> None:
    results = [Result((2,), True, False, False), Result((2,), True, True, True), Result((), False, True, False)]
    assert summarise(results) == {"total": 3, "cites_planted_count": 2, "no_marker_count": 2, "fallback_repaired_count": 1}


def test_fourteen_of_fifteen_keeps_the_model() -> None:
    assert decide({"total": 15, "cites_planted_count": 14, "no_marker_count": 2})[0] == "keep"


def test_thirteen_of_fifteen_switches_the_model() -> None:
    assert decide({"total": 15, "cites_planted_count": 13, "no_marker_count": 2}) == ("switch", "openai/gpt-4o-mini")


def test_three_no_marker_answers_switch_the_model() -> None:
    assert decide({"total": 15, "cites_planted_count": 15, "no_marker_count": 3})[0] == "switch"


def test_two_no_marker_answers_keep_the_model() -> None:
    assert decide({"total": 15, "cites_planted_count": 15, "no_marker_count": 2})[0] == "keep"
