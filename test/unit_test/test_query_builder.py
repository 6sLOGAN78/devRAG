"""Query builder: safe by construction, boosted fields, minimum_should_match 30 percent then 10 percent (RETR-02, RETR-03; R-196)."""

from __future__ import annotations

import re

import pytest

from common.doc_store.doc_store_base import MatchTextExpr
from common.settings import RetrievalSettings
from rag.nlp.query import FIELDS, QueryBuilder
from rag.nlp.tokenizer import tokenize

pytestmark = pytest.mark.unit


class StubSynonyms:
    def __init__(self, table: dict[str, list[str]] | None = None) -> None:
        self.table = table or {}
        self.asked: list[list[str]] = []

    def lookup_many(self, terms: list[str]) -> dict[str, list[str]]:
        self.asked.append(list(terms))
        return {t: list(self.table.get(t, [])) for t in terms}


def _builder(table: dict[str, list[str]] | None = None) -> QueryBuilder:
    return QueryBuilder(StubSynonyms(table), RetrievalSettings())


def test_fields_are_the_seven_boosted_names_in_order() -> None:
    assert FIELDS == [
        "title_tks^10",
        "title_sm_tks^5",
        "important_kwd^30",
        "important_tks^20",
        "question_tks^20",
        "content_ltks^2",
        "content_sm_ltks",
    ]


def test_text_expr_uses_thirty_percent_then_ten_percent_on_retry() -> None:
    plan = _builder().build("quarterly revenue forecast")
    expr = plan.text_expr(1024)
    assert isinstance(expr, MatchTextExpr)
    assert expr.fields == FIELDS and expr.fields is not FIELDS
    assert expr.topn == 1024
    assert expr.extra_options == {"minimum_should_match": "30%"}
    assert plan.text_expr(10, retry=True).extra_options == {"minimum_should_match": "10%"}


def test_percentages_come_from_settings() -> None:
    plan = QueryBuilder(None, RetrievalSettings(msm_percent=45, msm_retry_percent=5)).build("alpha beta")
    assert plan.text_expr(5).extra_options == {"minimum_should_match": "45%"}
    assert plan.text_expr(5, retry=True).extra_options == {"minimum_should_match": "5%"}


def test_tokens_are_deduplicated_in_order_without_stopwords() -> None:
    plan = _builder().build("What is the invoice total, and the invoice date?")
    assert plan.tokens == ("invoice", "total", "date")
    assert plan.expanded == plan.tokens
    assert not plan.empty


def test_synonyms_are_appended_as_plain_tokens() -> None:
    plan = _builder({"invoice": ["bill", "statement"]}).build("invoice total")
    assert plan.tokens == ("invoice", "total")
    assert plan.expanded == ("invoice", "total", "bill", "statement")
    assert plan.text_expr(10).matching_text == "invoice total bill statement"


def test_synonym_already_in_the_question_is_not_repeated() -> None:
    plan = _builder({"invoice": ["bill"]}).build("bill invoice")
    assert plan.expanded == ("bill", "invoice")


def test_no_synonym_source_means_no_expansion() -> None:
    assert QueryBuilder(None, RetrievalSettings()).build("invoice").expanded == ("invoice",)


@pytest.mark.parametrize("question", ["", "   ", "?!.,;", "--- *** ()", '"" ~~'])
def test_punctuation_only_gives_an_empty_plan(question: str) -> None:
    plan = _builder().build(question)
    assert plan.empty and plan.tokens == () and plan.expanded == ()
    with pytest.raises(ValueError):
        plan.text_expr(10)


@pytest.mark.parametrize("question", ["the", "what is the", "A an THE of"])
def test_stopword_only_question_falls_back_to_the_unfiltered_tokens(question: str) -> None:
    plan = _builder().build(question)
    assert not plan.empty
    assert list(plan.tokens) == list(dict.fromkeys(tokenize(question)))


def test_operators_and_quotes_never_reach_the_text() -> None:
    plan = _builder().build('"a OR b" -x * +y AND (z) NOT field:value ~2 \\')
    text = plan.text_expr(10).matching_text
    assert re.fullmatch(r"[\w ]+", text), text
    for ch in '"-*+()~:\\|&!^':
        assert ch not in text
    assert plan.tokens == tuple(dict.fromkeys(t for t in tokenize('"a OR b" -x * +y AND (z) NOT field:value ~2 \\') if t not in {"a", "or", "and", "not"}))


def test_builder_uses_the_shared_tokenizer_output() -> None:
    question = "Customer Refund Policy 2024"
    assert list(_builder().build(question).tokens) == list(dict.fromkeys(tokenize(question)))


def test_cjk_keeps_unigrams_and_bigrams() -> None:
    plan = _builder().build("合同金额")
    assert plan.tokens == ("合", "同", "金", "额", "合同", "同金", "金额")


def test_stopwords_are_dropped_only_from_latin_tokens() -> None:
    plan = _builder().build("the 合同")
    assert plan.tokens == ("合", "同", "合同")


def test_long_question_is_cut_to_the_first_64_distinct_tokens() -> None:
    question = " ".join(f"word{i}" for i in range(2000)) + " " + "x" * 3000
    assert len(question) > 5000
    plan = _builder().build(question)
    assert len(plan.tokens) == 64
    assert plan.tokens[0] == "word0" and plan.tokens[-1] == "word63"


def test_only_ascii_terms_are_sent_to_the_synonym_source() -> None:
    syn = StubSynonyms()
    QueryBuilder(syn, RetrievalSettings()).build("invoice 合同 total")
    assert syn.asked == [["invoice", "total"]]
