"""The Retriever over the real Elasticsearch adapter and the real Valkey (plan 05-03, D-22: no mocked engine).

Each test works in a random tenant index created by the adapter and removed by its recorded name at teardown. Vectors are planted
through the port so the golden fusion order is fixed by the weights alone.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from elasticsearch import Elasticsearch

from common.doc_store.doc_store_base import index_name
from common.settings import load_settings
from rag.chunking.types import Chunk
from rag.nlp.search import RetrievalRequest, Retriever
from rag.nlp.synonym import SynonymSource
from rag.nlp.token_count import count_tokens
from rag.svr.chunk_doc import build_row
from rag.utils.es_conn import ESConnection
from test.helpers.doc_store_contract import DIM, QUERY_VECTOR, RARE_KEYWORD, unit_vector

pytestmark = pytest.mark.integration

K_TEXT = f"field notes about {RARE_KEYWORD} samples"
S_TEXT = "plain unrelated sentence"


@pytest.fixture(scope="module")
def settings():
    return load_settings()


@pytest.fixture(scope="module")
def raw_client(settings) -> Iterator[Elasticsearch]:
    es = settings.es
    client = Elasticsearch(es.hosts, basic_auth=(es.username, es.password), request_timeout=30, max_retries=0)
    yield client
    client.close()


@pytest.fixture
def store(settings) -> ESConnection:
    return ESConnection(settings)


class World:
    """One tenant index with helpers to plant rows built by the real ingestion row builder."""

    def __init__(self, store: ESConnection, tenant_id: str) -> None:
        self.store = store
        self.tenant_id = tenant_id
        self.index = index_name(tenant_id)
        self.dataset = uuid.uuid4().hex
        store.create_idx(self.index, self.dataset, DIM, "naive")

    def add(self, name: str, text: str, axis: int, *, doc_id: str = "doc-1", dataset: str | None = None, enabled: bool = True, **extra) -> str:
        dataset = dataset or self.dataset
        chunk = Chunk(text, (), {}, count_tokens(text), 0)
        row = build_row(chunk, index=0, doc_id=doc_id, kb_id=dataset, doc_name=f"{doc_id}.txt", task_id="t", from_page=0, to_page=1, vector=unit_vector(axis), enabled=enabled)
        row["id"] = name
        row.update(extra)
        self.store.create_idx(self.index, dataset, DIM, "naive")
        assert self.store.insert([row], self.index, dataset) == []
        return name

    def plant_golden(self, **extra) -> None:
        self.add("chunk-k", K_TEXT, 1, **extra)
        self.add("chunk-s", S_TEXT, 0, **extra)

    def request(self, **overrides) -> RetrievalRequest:
        values = dict(
            tenant_id=self.tenant_id,
            dataset_ids=[self.dataset],
            question=RARE_KEYWORD,
            query_vector=list(QUERY_VECTOR),
            vector_dim=DIM,
            similarity_threshold=0.0,
        )
        values.update(overrides)
        return RetrievalRequest(**values)


@pytest.fixture
def world(store, raw_client) -> Iterator[World]:
    tenant_id = uuid.uuid4().hex
    yield World(store, tenant_id)
    raw_client.indices.delete(index=index_name(tenant_id), ignore_unavailable=True)
    assert raw_client.indices.exists(index=index_name(tenant_id)).body is False


@pytest.fixture
def retriever(store, settings) -> Retriever:
    return Retriever(store, settings)


def ids(result) -> list[str]:
    return [h.chunk_id for h in result.hits]


def test_golden_order_at_weight_zero_and_one(world, retriever):
    world.plant_golden()
    text_led = retriever.retrieve(world.request(vector_similarity_weight=0.0))
    assert ids(text_led) == ["chunk-k", "chunk-s"]
    assert text_led.hits[0].similarity == pytest.approx(1.0) and text_led.hits[1].similarity == pytest.approx(0.0)
    vector_led = retriever.retrieve(world.request(vector_similarity_weight=1.0))
    assert ids(vector_led) == ["chunk-s", "chunk-k"]
    assert vector_led.hits[0].vector_similarity == pytest.approx(1.0, abs=1e-3) and vector_led.hits[1].vector_similarity == pytest.approx(0.0, abs=1e-3)
    assert all(h.rerank_similarity is None for h in vector_led.hits) and vector_led.rerank_applied is False


def test_the_weighted_mix_scores_both_sides(world, retriever):
    world.plant_golden()
    out = retriever.retrieve(world.request(vector_similarity_weight=0.3))
    by_id = {h.chunk_id: h for h in out.hits}
    assert by_id["chunk-k"].similarity == pytest.approx(0.7, abs=1e-3)
    assert by_id["chunk-s"].similarity == pytest.approx(0.3, abs=1e-3)


def test_threshold_removes_weak_hits_and_total_follows(world, retriever):
    world.plant_golden()
    out = retriever.retrieve(world.request(vector_similarity_weight=0.0, similarity_threshold=0.5))
    assert ids(out) == ["chunk-k"] and out.total == 1


def test_disabled_chunks_and_disabled_documents_never_appear(world, retriever):
    world.add("live", K_TEXT, 1)
    world.add("unavailable", K_TEXT, 1, available_int=0)
    world.add("doc-off", K_TEXT, 1, doc_id="doc-off", enabled=False)
    out = retriever.retrieve(world.request())
    assert ids(out) == ["live"]


def test_removed_kwd_rows_are_excluded(world, retriever):
    world.add("kept", K_TEXT, 1)
    world.add("same-row-no-field", K_TEXT, 2, doc_id="doc-2")
    world.add("removed", K_TEXT, 1, doc_id="doc-3", removed_kwd="Y")
    out = retriever.retrieve(world.request())
    assert set(ids(out)) == {"kept", "same-row-no-field"}
    assert out.total == 2


def test_a_doc_id_must_not_list_excludes_the_documents_through_the_engine(world):
    from common.doc_store.doc_store_base import FusionExpr, MatchDenseExpr, MatchTextExpr

    world.add("a", K_TEXT, 1, doc_id="doc-a")
    world.add("b", K_TEXT, 0, doc_id="doc-b")
    world.add("c", K_TEXT, 2, doc_id="doc-c")
    matches = [
        MatchTextExpr(["content_ltks"], RARE_KEYWORD, 10),
        MatchDenseExpr(f"q_{DIM}_vec", list(QUERY_VECTOR), "float", "cosine", 10, {"similarity": 0.0}),
        FusionExpr("weighted_sum", 10, {"weights": "0.001,1"}),
    ]
    found = world.store.search(["doc_id"], [], {"available_int": 1, "must_not": {"doc_id": ["doc-a", "doc-b"]}}, matches, None, 0, 10, world.index, [world.dataset])
    assert [h["id"] for h in found.hits] == ["c"]


def test_deleted_document_is_pruned(world, retriever):
    world.add("alive", K_TEXT, 1, doc_id="doc-alive")
    world.add("gone", K_TEXT, 1, doc_id="doc-gone")
    asked: list[set[str]] = []

    def exists(doc_ids: set[str]) -> set[str]:
        asked.append(set(doc_ids))
        return doc_ids - {"doc-gone"}

    out = retriever.retrieve(world.request(), document_exists=exists)
    assert ids(out) == ["alive"] and asked == [{"doc-alive", "doc-gone"}]


def test_doc_ids_narrow_the_search(world, retriever):
    world.add("one", K_TEXT, 1, doc_id="doc-1")
    world.add("two", K_TEXT, 1, doc_id="doc-2")
    out = retriever.retrieve(world.request(doc_ids=["doc-2"]))
    assert ids(out) == ["two"]


def test_foreign_dataset_id_returns_nothing(world, retriever):
    world.plant_golden()
    foreign = uuid.uuid4().hex  # a dataset id that holds no rows in this tenant's index
    out = retriever.retrieve(world.request(dataset_ids=[foreign]))
    assert out.total == 0 and out.hits == []


def test_two_datasets_of_one_tenant_are_both_searched(world, retriever):
    second = uuid.uuid4().hex
    world.add("in-first", K_TEXT, 1)
    world.add("in-second", K_TEXT, 1, dataset=second)
    both = retriever.retrieve(world.request(dataset_ids=[world.dataset, second]))
    assert set(ids(both)) == {"in-first", "in-second"}
    assert {h.dataset_id for h in both.hits} == {world.dataset, second}
    only_first = retriever.retrieve(world.request())
    assert ids(only_first) == ["in-first"]


def test_a_reranker_changes_the_order_and_marks_the_result(world, retriever):
    world.plant_golden()
    plain = retriever.retrieve(world.request(vector_similarity_weight=0.8))
    assert ids(plain) == ["chunk-s", "chunk-k"]
    asked: list[tuple[str, list[str]]] = []

    def reranker(query: str, texts: list[str]) -> list[float]:
        asked.append((query, list(texts)))
        return [0.9 if RARE_KEYWORD in text else 0.1 for text in texts]

    reranked = retriever.retrieve(world.request(vector_similarity_weight=0.8), reranker=reranker)
    assert ids(reranked) == ["chunk-k", "chunk-s"] and reranked.rerank_applied is True
    assert {h.chunk_id: h.rerank_similarity for h in reranked.hits} == pytest.approx({"chunk-k": 0.9, "chunk-s": 0.1})
    assert len(asked) == 1 and sorted(asked[0][1]) == sorted([K_TEXT, S_TEXT])
    assert reranked.hits[0].similarity == pytest.approx(0.2 * 1.0 + 0.8 * 0.9, abs=1e-6)


def test_only_the_rerank_cap_candidates_are_reranked_and_the_rest_are_dropped(world, retriever):
    world.plant_golden()
    out = retriever.retrieve(world.request(vector_similarity_weight=0.8, rerank_cap=1), reranker=lambda q, texts: [0.5] * len(texts))
    assert len(out.hits) == 1 and out.hits[0].chunk_id == "chunk-s" and out.rerank_applied is True


def test_a_failing_reranker_propagates(world, retriever):
    world.plant_golden()

    def failing(query: str, texts: list[str]) -> list[float]:
        raise TimeoutError("provider timed out")

    with pytest.raises(TimeoutError):
        retriever.retrieve(world.request(), reranker=failing)


def test_rrf_returns_the_same_chunk_set_and_keeps_scored_similarities(world, retriever):
    world.plant_golden()
    weighted = retriever.retrieve(world.request(vector_similarity_weight=0.3))
    fused = retriever.retrieve(world.request(vector_similarity_weight=0.3, fusion="rrf"))
    assert set(ids(fused)) == set(ids(weighted)) == {"chunk-k", "chunk-s"}
    assert {h.chunk_id: h.similarity for h in fused.hits} == pytest.approx({h.chunk_id: h.similarity for h in weighted.hits})


def test_pagination_slices_a_stable_order(world, retriever):
    for i in range(5):
        world.add(f"p{i}", f"{K_TEXT} number {i}", i % DIM, doc_id=f"doc-{i}")
    whole = ids(retriever.retrieve(world.request(size=10)))
    assert len(whole) == 5
    pages = [retriever.retrieve(world.request(size=2, page=n)) for n in (1, 2, 3)]
    assert all(p.total == 5 for p in pages)
    assert [len(p.hits) for p in pages] == [2, 2, 1]
    assert [cid for p in pages for cid in ids(p)] == whole


def test_a_question_with_no_searchable_words_does_not_reach_the_engine(world, retriever):
    world.plant_golden()
    out = retriever.retrieve(world.request(question="?! ..."))
    assert out.total == 0 and out.hits == []


def test_the_retriever_leaves_the_index_unchanged(world, retriever, raw_client):
    world.plant_golden()
    before = raw_client.count(index=world.index).body["count"]
    retriever.retrieve(world.request())
    assert raw_client.count(index=world.index).body["count"] == before
    row = world.store.get("chunk-k", world.index, [world.dataset])
    assert row is not None and row["available_int"] == 1


def test_synonym_source_answers_from_the_real_valkey_and_caches(settings):
    import valkey

    from common.settings import RetrievalSettings

    term = "invoice"
    source = SynonymSource(settings.redis, RetrievalSettings())
    first = source.lookup(term)
    assert first, "the in-repo dictionary has synonyms for this term"
    client = valkey.Valkey(host=settings.redis.host, port=settings.redis.port, password=settings.redis.password or None, db=settings.redis.db, socket_timeout=5)
    try:
        cached = client.get(f"synonym_{term}")
        assert cached is not None
        assert source.lookup(term) == first
        assert client.ttl(f"synonym_{term}") > 0
    finally:
        client.delete(f"synonym_{term}")
        client.close()
