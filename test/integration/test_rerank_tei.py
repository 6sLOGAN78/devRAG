"""Real CPU TEI and Elasticsearch proofs; a missing service fails rather than skips."""
from __future__ import annotations

import asyncio
import os
import uuid

import httpx
import pytest
from elasticsearch import Elasticsearch

from common.doc_store.doc_store_base import index_name
from common.settings import LlmSettings, load_settings
from rag.llm import resolve_provider
from rag.llm.rerank_model import TEIRerank
from rag.nlp.search import Retriever
from rag.utils.es_conn import ESConnection
from test.helpers.wait import wait_until
from test.integration.test_retrieval_es import World

pytestmark = pytest.mark.integration
BASE = f"http://127.0.0.1:{os.environ.get('TEI_PORT', '6381')}"
QUESTION = "What is the capital of France?"
KEYWORDS = "capital capital France France France is a country in western Europe known for wine and cheese"
ANSWER = "Paris is the seat of government of the French republic"


@pytest.fixture(scope="module", autouse=True)
def ready():
    with httpx.Client(timeout=3) as client:
        def health():
            try:
                return client.get(f"{BASE}/health").status_code == 200
            except httpx.HTTPError:
                return False
        wait_until(health, timeout=120, describe=lambda: "real TEI on loopback port is required")


def driver(kind=TEIRerank):
    return kind(resolve_provider("TEI"), "BAAI/bge-reranker-base", None, BASE, llm_settings=LlmSettings(max_retries=0), allow_private=True, timeout=120)


def rank(texts, question=QUESTION):
    return asyncio.run(driver().similarity(question, texts))


def test_tei_health():
    assert httpx.get(f"{BASE}/health").status_code == 200


def test_relevant_text_scores_above_irrelevant_text():
    scores = rank([ANSWER, "Bananas are yellow."]).scores
    assert scores[0] > scores[1]
    assert all(0 <= score <= 1 for score in scores)


def test_seventy_texts_reach_the_real_server_in_batches_of_32_32_6():
    sizes = []

    class RecordingTEI(TEIRerank):
        def _request(self, query, batch):
            sizes.append(len(batch))
            return super()._request(query, batch)

    result = asyncio.run(driver(RecordingTEI).similarity(QUESTION, [ANSWER, "Bananas are yellow."] * 35))
    assert sizes == [32, 32, 6]
    assert len(result.scores) == 70
    assert all(result.scores[i] > result.scores[i + 1] for i in range(0, 70, 2))


def test_long_text_is_truncated_instead_of_rejected():
    result = rank(["A document about the French republic and Paris. " * 400])
    assert len(result.scores) == 1 and 0 <= result.scores[0] <= 1


def test_empty_text_list_has_no_usage():
    result = rank([])
    assert result.scores == [] and result.tokens == 0


def test_empty_question_returns_zero_scores_without_inference():
    result = rank([ANSWER], question=" ")
    assert result.scores == [0] and result.tokens == 0


def test_input_order_is_preserved_for_scores():
    scores = rank(["Bananas are yellow.", ANSWER]).scores
    assert scores[1] > scores[0]


def test_reranked_order_differs_from_fusion_order():
    settings = load_settings()
    store = ESConnection(settings)
    es = settings.es
    client = Elasticsearch(es.hosts, basic_auth=(es.username, es.password), max_retries=0)
    world = World(store, uuid.uuid4().hex)
    try:
        world.add("chunk-k", KEYWORDS, 0)
        world.add("chunk-a", ANSWER, 0)
        request = world.request(question=QUESTION, vector_similarity_weight=0.8)
        retriever = Retriever(store, settings)
        plain = retriever.retrieve(request)
        assert [hit.chunk_id for hit in plain.hits] == ["chunk-k", "chunk-a"]
        ranked = retriever.retrieve(request, reranker=lambda query, texts: rank(texts, query).scores)
        assert ranked.rerank_applied
        assert [hit.chunk_id for hit in ranked.hits] == ["chunk-a", "chunk-k"]
        assert ranked.hits[0].rerank_similarity > ranked.hits[1].rerank_similarity
    finally:
        client.indices.delete(index=index_name(world.tenant_id), ignore_unavailable=True)
        client.close()
