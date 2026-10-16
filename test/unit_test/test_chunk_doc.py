from __future__ import annotations

import math
import re

import pytest

from rag.chunking.types import Chunk
from rag.nlp.token_count import count_tokens
from rag.nlp.tokenizer import tokenize
from rag.parsers.types import PageBox
from rag.svr.chunk_doc import build_row, l2_normalize, manual_chunk_id, parsed_chunk_id
from rag.svr.failure import TaskFailure

pytestmark = pytest.mark.unit

DOC = "d" * 32
PARSED = re.compile(r"^[0-9a-f]{32}_[0-9]+$")
MANUAL = re.compile(r"^[0-9a-f]{32}_m_[0-9a-f]{32}$")


def test_parsed_chunk_id_uses_the_task_span():
    assert parsed_chunk_id(DOC, 12, 3, 13) == f"{DOC}_12003"
    assert parsed_chunk_id(DOC, 12, 999, 13) == f"{DOC}_12999"


def test_index_over_the_page_cap_is_terminal():
    with pytest.raises(TaskFailure) as err:
        parsed_chunk_id(DOC, 12, 1000, 13)
    assert err.value.code == "too_many_chunks" and err.value.terminal


def test_a_single_task_non_pdf_is_not_capped_at_1000():
    assert parsed_chunk_id(DOC, 0, 1500, 1000000) == f"{DOC}_1500"


def test_manual_and_parsed_grammars_are_disjoint():
    parsed, manual = parsed_chunk_id(DOC, 0, 1, 1000000), manual_chunk_id(DOC)
    assert MANUAL.match(manual) and PARSED.match(parsed)
    assert not MANUAL.match(parsed) and not PARSED.match(manual)


def test_l2_normalize_gives_unit_length():
    out = l2_normalize([3.0, 4.0])
    assert abs(math.sqrt(sum(x * x for x in out)) - 1.0) < 1e-6


@pytest.mark.parametrize("vector", [[0.0, 0.0], [1.0, float("nan")], [float("inf"), 1.0]])
def test_bad_vectors_are_refused(vector):
    with pytest.raises(TaskFailure) as err:
        l2_normalize(vector)
    assert (err.value.step, err.value.code) == ("embed", "provider_refused")


def test_build_row_has_the_documented_fields():
    text = "Hello world. Second sentence here."
    chunk = Chunk(
        text,
        (PageBox(1, 10, 20, 30, 40), PageBox(2, 5, 6, 7, 8)),
        {1: (595.0, 842.0), 2: (595.0, 842.0)},
        count_tokens(text),
        0,
    )
    row = build_row(chunk, index=3, doc_id=DOC, kb_id="k" * 32, doc_name="report.pdf", task_id="t" * 32, from_page=0, to_page=12, vector=[1.0, 0.0], enabled=True)
    assert row["id"] == f"{DOC}_3" and row["order_int"] == 3
    assert row["position_int"] == [[1, 10, 20, 30, 40], [2, 5, 6, 7, 8]]
    assert row["page_num_int"] == [1, 2] and row["top_int"] == 20
    assert row["page_dims_flt"] == [[1.0, 595.0, 842.0], [2.0, 595.0, 842.0]]
    assert row["available_int"] == 1 and row["doc_enabled_int"] == 1 and row["origin_kwd"] == "parsed"
    assert row["token_num_int"] == count_tokens(text)
    assert row["content_ltks"] == " ".join(tokenize(text))
    assert row["docnm_kwd"] == "report.pdf" and row["content_with_weight"] == text
    assert row["q_2_vec"] == [1.0, 0.0] and row["task_id"] == "t" * 32
    expected = (
        "id doc_id kb_id docnm_kwd content_with_weight content_ltks content_sm_ltks title_tks title_sm_tks position_int page_num_int top_int "
        "available_int q_2_vec create_time create_timestamp_flt order_int task_id origin_kwd token_num_int doc_enabled_int page_dims_flt"
    ).split()
    assert set(row) == set(expected)


def test_disabled_document_sets_doc_enabled_zero():
    chunk = Chunk("abc", (), {}, 1, 0)
    row = build_row(chunk, index=0, doc_id=DOC, kb_id="k" * 32, doc_name="a.txt", task_id="t" * 32, from_page=0, to_page=1000000, vector=[1.0], enabled=False)
    assert row["doc_enabled_int"] == 0 and row["position_int"] == [] and row["top_int"] == 0
