"""Call shapes of the Retriever (plan 05-03). The in-memory store below only records calls; behaviour is proved on the real engine in
``test/integration/test_retrieval_es.py``."""
from __future__ import annotations

import pytest

from common.doc_store.doc_store_base import DocStoreConnection, DocStoreError, FusionExpr, MatchDenseExpr, MatchTextExpr, SearchResult, StatsResult
from common.settings import RetrievalSettings
from rag.nlp.search import Hit, RetrievalRequest, RetrievalResult, Retriever

pytestmark = pytest.mark.unit

TENANT = "a" * 32
DATASET = "b" * 32
DIM = 4
VECTOR = [1.0, 0.0, 0.0, 0.0]


class RecordingStore(DocStoreConnection):
    """Answers searches from a queue of canned results and records every call."""

    def __init__(self, answers: list[SearchResult | Exception]) -> None:
        self.answers = list(answers)
        self.calls: list[dict] = []
        self.writes = 0

    def search(self, select_fields, highlight_fields, condition, match_expressions, order_by, offset, limit, index_names, dataset_ids, agg_fields=None, rank_feature=None):
        self.calls.append({"select": select_fields, "condition": condition, "matches": match_expressions, "limit": limit, "index": index_names, "datasets": dataset_ids})
        answer = self.answers.pop(0) if self.answers else SearchResult(0, [], {})
        if isinstance(answer, Exception):
            raise answer
        return answer

    def update(self, condition, new_value, index_name, dataset_id):
        self.writes += 1
        return True

    def insert(self, rows, index_name, dataset_id):
        self.writes += 1
        return []

    def delete(self, condition, index_name, dataset_id):
        self.writes += 1
        return 0

    def db_type(self):
        return "fake"

    def health(self):
        return {"status": "ok", "type": "fake"}

    def create_idx(self, index_name, dataset_id, vector_size, parser_id=None):
        return True

    def delete_idx(self, index_name, dataset_id):
        return None

    def index_exist(self, index_name, dataset_id=None):
        return True

    def get(self, chunk_id, index_name, dataset_ids):
        return None

    def stats(self, condition, index_name, dataset_id, sum_field=None):
        return StatsResult(0, 0.0)


def hit(chunk_id: str, doc_id: str = "d1", text: str = "ledger notes", score: float = 1.0) -> dict:
    return {
        "id": chunk_id,
        "doc_id": doc_id,
        "kb_id": DATASET,
        "docnm_kwd": "file.txt",
        "content_with_weight": text,
        "content_ltks": text,
        "title_tks": "file",
        "position_int": [],
        "page_num_int": [],
        "page_dims_flt": [],
        "_score": score,
    }


def request(**overrides) -> RetrievalRequest:
    values = dict(tenant_id=TENANT, dataset_ids=[DATASET], question="ledger notes", query_vector=VECTOR, vector_dim=DIM, similarity_threshold=0.0)
    values.update(overrides)
    return RetrievalRequest(**values)


def retriever(store: RecordingStore) -> Retriever:
    return Retriever(store, RetrievalSettings())


def result(*hits: dict) -> SearchResult:
    return SearchResult(len(hits), list(hits), {})


def test_stage_one_expression_order_condition_and_fusion_weights():
    store = RecordingStore([result(hit("c1")), result(hit("c1", score=1.0))])
    out = retriever(store).retrieve(request())
    first = store.calls[0]
    text, dense, fusion = first["matches"]
    assert isinstance(text, MatchTextExpr) and isinstance(dense, MatchDenseExpr) and isinstance(fusion, FusionExpr)
    assert dense.vector_column_name == f"q_{DIM}_vec" and dense.extra_options == {"similarity": 0.0}
    assert fusion.method == "weighted_sum" and fusion.fusion_params == {"weights": "0.001,1"}
    assert first["condition"] == {"available_int": 1, "doc_enabled_int": 1, "must_not": {"removed_kwd": "Y"}}
    assert first["datasets"] == [DATASET]
    assert isinstance(out, RetrievalResult) and [h.chunk_id for h in out.hits] == ["c1"]


def test_generated_only_terms_contribute_to_product_text_score():
    row = {**hit("generated", text="lighthouse measurements"), "important_tks": "beacon altitude", "question_tks": "how tall is the beacon"}
    store = RecordingStore([result(row), result(hit("generated", score=1.0))])
    out = retriever(store).retrieve(request(question="beacon altitude", vector_similarity_weight=0.0, similarity_threshold=0.5))
    assert [item.chunk_id for item in out.hits] == ["generated"]
    assert out.hits[0].term_similarity == 1.0
    assert "important_tks" in store.calls[0]["select"] and "question_tks" in store.calls[0]["select"]


def test_stage_two_is_a_knn_only_search_over_the_candidate_ids():
    store = RecordingStore([result(hit("c1"), hit("c2")), result(hit("c2", score=1.0), hit("c1", score=0.75))])
    out = retriever(store).retrieve(request(vector_similarity_weight=1.0))
    second = store.calls[1]
    assert second["condition"] == {"id": ["c1", "c2"], "must_not": {"removed_kwd": "Y"}}
    assert second["limit"] == 2
    assert len(second["matches"]) == 1 and isinstance(second["matches"][0], MatchDenseExpr)
    assert second["matches"][0].extra_options == {"similarity": 0.0}
    assert [h.chunk_id for h in out.hits] == ["c2", "c1"]
    assert out.hits[0].vector_similarity == pytest.approx(1.0) and out.hits[1].vector_similarity == pytest.approx(0.5)


def test_doc_ids_join_the_condition_and_an_empty_list_returns_nothing():
    store = RecordingStore([result(hit("c1")), result(hit("c1"))])
    retriever(store).retrieve(request(doc_ids=["d1", "d2"]))
    assert store.calls[0]["condition"]["doc_id"] == ["d1", "d2"]
    empty = RecordingStore([])
    assert retriever(empty).retrieve(request(doc_ids=[])).hits == [] and empty.calls == []


def test_an_empty_plan_does_not_call_the_engine():
    store = RecordingStore([])
    out = retriever(store).retrieve(request(question="?! ..."))
    assert out.hits == [] and out.total == 0 and out.rerank_applied is False
    assert store.calls == []


def test_the_ten_percent_retry_runs_once_when_stage_one_is_empty():
    store = RecordingStore([result(), result()])
    out = retriever(store).retrieve(request())
    assert out.total == 0 and len(store.calls) == 2
    assert store.calls[0]["matches"][0].extra_options == {"minimum_should_match": "30%"}
    assert store.calls[1]["matches"][0].extra_options == {"minimum_should_match": "10%"}


def test_document_exists_prunes_before_stage_two():
    seen: list[set[str]] = []

    def exists(ids):
        seen.append(set(ids))
        return {"d1"}

    store = RecordingStore([result(hit("c1", "d1"), hit("c2", "d2")), result(hit("c1"))])
    out = retriever(store).retrieve(request(), document_exists=exists)
    assert seen == [{"d1", "d2"}] and [h.chunk_id for h in out.hits] == ["c1"]
    assert store.calls[1]["condition"]["id"] == ["c1"]


def test_the_retriever_never_writes():
    store = RecordingStore([result(hit("c1")), result(hit("c1"))])
    retriever(store).retrieve(request())
    assert store.writes == 0


def test_a_store_error_propagates_unchanged():
    boom = DocStoreError("document store search failed")
    with pytest.raises(DocStoreError) as err:
        retriever(RecordingStore([boom])).retrieve(request())
    assert err.value is boom


def test_a_reranker_error_propagates_and_a_wrong_length_is_refused():
    def failing(query, texts):
        raise TimeoutError("provider")

    store = RecordingStore([result(hit("c1")), result(hit("c1"))])
    with pytest.raises(TimeoutError):
        retriever(store).retrieve(request(), reranker=failing)
    store = RecordingStore([result(hit("c1")), result(hit("c1"))])
    with pytest.raises(ValueError):
        retriever(store).retrieve(request(), reranker=lambda q, t: [0.5, 0.5])
    store = RecordingStore([result(hit("c1")), result(hit("c1"))])
    with pytest.raises(ValueError):
        retriever(store).retrieve(request(), reranker=lambda q, t: [float("nan")])


def test_only_the_rerank_cap_best_candidates_are_reranked_and_the_rest_dropped():
    texts: list[list[str]] = []

    def reranker(query, batch):
        texts.append(list(batch))
        return [0.9] * len(batch)

    hits = [hit(f"c{i}", text=f"ledger notes {i}") for i in range(4)]
    stage_two = [hit(f"c{i}", score=1.0 - 0.1 * i) for i in range(4)]
    store = RecordingStore([result(*hits), result(*stage_two)])
    out = retriever(store).retrieve(request(rerank_cap=2), reranker=reranker)
    assert len(texts) == 1 and len(texts[0]) == 2
    assert out.rerank_applied is True and len(out.hits) == 2
    assert all(h.rerank_similarity == pytest.approx(0.9) for h in out.hits)


def test_rrf_runs_a_text_search_and_a_knn_search_without_a_fusion_expression():
    store = RecordingStore([result(hit("c1")), result(hit("c2")), result(hit("c1"), hit("c2"))])
    out = retriever(store).retrieve(request(fusion="rrf"))
    text_call, dense_call, rescore = store.calls
    assert [type(m) for m in text_call["matches"]] == [MatchTextExpr]
    assert [type(m) for m in dense_call["matches"]] == [MatchDenseExpr]
    assert rescore["condition"]["id"] == ["c1", "c2"] or rescore["condition"]["id"] == ["c2", "c1"]
    assert {h.chunk_id for h in out.hits} == {"c1", "c2"}


def test_request_validation_rejects_out_of_range_numbers():
    for bad in ({"vector_similarity_weight": 1.5}, {"similarity_threshold": -0.1}, {"top_k": 0}, {"page": 0}, {"size": 0}, {"fusion": "other"}, {"rerank_cap": 0}):
        with pytest.raises(ValueError):
            request(**bad)


def test_hit_is_frozen_and_scores_are_finite():
    store = RecordingStore([result(hit("c1")), result(hit("c1", score=float("inf")))])
    out = retriever(store).retrieve(request())
    h = out.hits[0]
    assert isinstance(h, Hit) and h.rerank_similarity is None
    assert all(v == v and abs(v) != float("inf") for v in (h.similarity, h.term_similarity, h.vector_similarity))
