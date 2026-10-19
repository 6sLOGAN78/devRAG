"""Plan 05-01: the planted-fact corpus (D-07). Each fact is a unique token that appears in exactly one chunk-sized unit."""
from __future__ import annotations

import io
import re

import pypdfium2 as pdfium
import pytest

from test.helpers.planted import FACTS, PDF_FACTS, off_topic_question, planted_pdf, planted_txt

pytestmark = pytest.mark.unit


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text.lower()))


def _paragraphs() -> list[str]:
    return planted_txt().decode("utf-8").split("\n\n")


def _pdf_pages() -> list[str]:
    document = pdfium.PdfDocument(io.BytesIO(planted_pdf()))
    try:
        return [page.get_textpage().get_text_bounded() for page in (document[i] for i in range(len(document)))]
    finally:
        document.close()


def test_six_facts_and_six_paragraphs() -> None:
    assert len(FACTS) == 6
    assert len(_paragraphs()) == 6
    assert len({f.token for f in FACTS}) == 6


def test_each_txt_fact_token_and_answer_appear_in_exactly_one_paragraph() -> None:
    paragraphs = _paragraphs()
    for index, fact in enumerate(FACTS):
        assert fact.keywords, fact
        for needle in (fact.token, *fact.keywords):
            hits = [i for i, p in enumerate(paragraphs) if re.search(rf"(?<![\w-]){re.escape(needle)}(?![\w-])", p)]
            assert hits == [index], f"{needle!r} should be only in paragraph {index}, found in {hits}"


def test_each_question_names_its_own_token_only() -> None:
    for fact in FACTS:
        assert fact.token in fact.question
        others = [f.token for f in FACTS if f is not fact]
        assert not any(token in fact.question for token in others)


def test_the_pdf_has_three_pages_and_each_page_holds_only_its_own_fact() -> None:
    pages = _pdf_pages()
    assert len(pages) == 3
    assert sorted(PDF_FACTS) == [1, 2, 3]
    for number, fact in PDF_FACTS.items():
        own = pages[number - 1]
        assert fact.token in own, f"page {number} lacks {fact.token}"
        for needle in fact.keywords:
            assert re.search(rf"(?<![\w-]){re.escape(needle)}(?![\w-])", own)
        for other_number, other in PDF_FACTS.items():
            if other_number != number:
                assert other.token not in own
                assert not any(re.search(rf"(?<![\w-]){re.escape(k)}(?![\w-])", own) for k in other.keywords if k != "the")


def test_pdf_and_txt_facts_do_not_overlap() -> None:
    txt = planted_txt().decode("utf-8")
    pdf_text = " ".join(_pdf_pages())
    for fact in PDF_FACTS.values():
        assert fact.token not in txt
    for fact in FACTS:
        assert fact.token not in pdf_text


def test_the_off_topic_question_shares_no_word_with_any_text() -> None:
    question_words = _words(off_topic_question())
    assert question_words
    corpus = _words(planted_txt().decode("utf-8")) | _words(" ".join(_pdf_pages()))
    assert not (question_words & corpus), sorted(question_words & corpus)


def test_controlled_vector_rows_split_the_text_and_dense_sides() -> None:
    from test.helpers.doc_store_contract import QUERY_VECTOR, RARE_KEYWORD, planted_vector_rows

    keyword_row, vector_row = planted_vector_rows(16)
    assert RARE_KEYWORD in keyword_row["content_ltks"] and RARE_KEYWORD not in vector_row["content_ltks"]
    assert vector_row["q_16_vec"][:8] == QUERY_VECTOR and sum(vector_row["q_16_vec"]) == 1.0
    assert keyword_row["q_16_vec"][1] == 1.0 and keyword_row["q_16_vec"] != vector_row["q_16_vec"]
