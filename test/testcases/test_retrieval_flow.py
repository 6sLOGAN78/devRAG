"""Retrieval test end to end through Nginx on the running stack (plan 05-04; RETR-16..18, RETR-23, KB-18, TEN-03, E2E-07 API half, D-19, D-20).

Nothing of devRag is replaced: Nginx, the app, the task executor, MySQL, MinIO, Valkey and Elasticsearch are the running stack. The loopback provider is the
third party's end of the embedding wire. It answers near-identical vectors, so these tests prove the arithmetic of the three scores and the filters
(threshold, documents, switches, pages, isolation); the order change between weights with real meaning is proved with planted vectors in
``test/integration/test_retrieval_es.py`` and in the live tier.
"""
from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from test.helpers.accounts import Account, AccountRegistry
from test.helpers.fake_provider import FakeProvider, running_stack_fake_provider
from test.helpers.ingest import start_parse, upload_text, wait_run
from test.helpers.planted import FACTS, planted_txt
from test.testcases.conftest import BASE_URL
from test.testcases.test_dataset_flow import create, workspace
from test.testcases.test_provider_flow import KEY_ONE, NOT_FOUND, _bearer, api, join, ok

pytestmark = pytest.mark.e2e

SEARCH = "/api/v1/datasets/search"
EMBEDDINGS = "/v1/embeddings"
HIT_KEYS = {
    "chunk_id", "doc_id", "doc_name", "dataset_id", "content", "positions", "page_sizes", "similarity", "term_similarity", "vector_similarity",
}  # fmt: skip
FIRST = FACTS[0]


@pytest.fixture(scope="module")
def fake() -> Iterator[FakeProvider]:
    with running_stack_fake_provider() as provider:
        yield provider


@pytest.fixture(scope="module")
def registry(ingress: httpx.Client) -> Iterator[AccountRegistry]:
    accounts = AccountRegistry(BASE_URL)
    try:
        yield accounts
    finally:
        accounts.cleanup()


@pytest.fixture(scope="module")
def owner(ingress: httpx.Client, registry: AccountRegistry, fake: FakeProvider) -> Account:
    return workspace(ingress, registry, fake, "retr")


@pytest.fixture(scope="module")
def planted(ingress: httpx.Client, owner: Account) -> SimpleNamespace:
    """A dataset holding the planted TXT (six paragraphs, six chunks), parsed and finished."""
    dataset_id = ok(create(ingress, owner))["id"]
    doc = upload_text(ingress, owner, dataset_id, planted_txt(), "planted.txt")
    assert start_parse(ingress, owner, dataset_id, [doc["id"]]).status_code == 200
    row = wait_run(ingress, owner, dataset_id, doc["id"], "3", timeout=180)
    assert row["chunk_count"] == len(FACTS)
    return SimpleNamespace(dataset_id=dataset_id, doc_id=doc["id"])


def search(ingress: httpx.Client, who: Account, dataset_ids: list[str], question: str, **body: Any) -> httpx.Response:
    return api(ingress, "POST", SEARCH, who.token, body={"dataset_ids": dataset_ids, "question": question, **body})


def hits_of(ingress: httpx.Client, who: Account, where: SimpleNamespace, question: str, **body: Any) -> list[dict[str, Any]]:
    return ok(search(ingress, who, [where.dataset_id], question, **body))["chunks"]


def keyword_question() -> str:
    return f"{FIRST.token} reactor coolant"


# ----------------------------------------------------------------------------- shape and scores


def test_a_keyword_question_at_weight_zero_returns_the_planted_chunk_first(ingress: httpx.Client, owner: Account, planted: SimpleNamespace) -> None:
    data = ok(search(ingress, owner, [planted.dataset_id], FIRST.question, vector_similarity_weight=0, similarity_threshold=0))
    assert set(data) == {"total", "chunks", "doc_aggs", "rerank_applied", "timings"} and data["rerank_applied"] is False
    assert set(data["timings"]) == {"embed_ms", "search_ms", "rerank_ms"}
    first = data["chunks"][0]
    assert HIT_KEYS <= set(first) and FIRST.token in first["content"]
    assert first["doc_id"] == planted.doc_id and first["doc_name"] == "planted.txt" and first["dataset_id"] == planted.dataset_id
    assert all(c["similarity"] == c["term_similarity"] for c in data["chunks"]), "weight 0 scores by the keyword share"
    assert data["doc_aggs"] == [{"doc_id": planted.doc_id, "doc_name": "planted.txt", "count": len(data["chunks"])}]


def test_every_planted_question_finds_its_own_paragraph_first(ingress: httpx.Client, owner: Account, planted: SimpleNamespace) -> None:
    for fact in FACTS:
        found = hits_of(ingress, owner, planted, fact.question, vector_similarity_weight=0, similarity_threshold=0)
        assert fact.token in found[0]["content"], fact.token


def test_at_weight_one_the_score_is_the_vector_share_and_the_hits_are_sorted_by_it(ingress: httpx.Client, owner: Account, planted: SimpleNamespace) -> None:
    found = hits_of(ingress, owner, planted, FIRST.question, vector_similarity_weight=1, similarity_threshold=0)
    assert len(found) == len(FACTS)
    assert all(abs(c["similarity"] - c["vector_similarity"]) < 1e-9 for c in found)
    scores = [c["similarity"] for c in found]
    assert scores == sorted(scores, reverse=True)


def test_a_higher_threshold_returns_fewer_hits(ingress: httpx.Client, owner: Account, planted: SimpleNamespace) -> None:
    wide = ok(search(ingress, owner, [planted.dataset_id], keyword_question(), vector_similarity_weight=0, similarity_threshold=0))
    strict = ok(search(ingress, owner, [planted.dataset_id], keyword_question(), vector_similarity_weight=0, similarity_threshold=0.99))
    assert wide["total"] > strict["total"] >= 1
    assert all(c["term_similarity"] >= 0.99 and FIRST.token in c["content"] for c in strict["chunks"])


def test_doc_ids_narrow_the_search_and_an_unknown_document_finds_nothing(ingress: httpx.Client, owner: Account, planted: SimpleNamespace) -> None:
    kept = hits_of(ingress, owner, planted, keyword_question(), doc_ids=[planted.doc_id], similarity_threshold=0)
    assert kept and {c["doc_id"] for c in kept} == {planted.doc_id}
    assert hits_of(ingress, owner, planted, keyword_question(), doc_ids=["0" * 32], similarity_threshold=0) == []


def test_page_two_of_size_two_is_stable_and_does_not_repeat_page_one(ingress: httpx.Client, owner: Account, planted: SimpleNamespace) -> None:
    first = ok(search(ingress, owner, [planted.dataset_id], FIRST.question, size=2, page=1, similarity_threshold=0))
    second = ok(search(ingress, owner, [planted.dataset_id], FIRST.question, size=2, page=2, similarity_threshold=0))
    again = ok(search(ingress, owner, [planted.dataset_id], FIRST.question, size=2, page=2, similarity_threshold=0))
    assert first["total"] == second["total"] == len(FACTS) and len(first["chunks"]) == len(second["chunks"]) == 2
    assert not {c["chunk_id"] for c in first["chunks"]} & {c["chunk_id"] for c in second["chunks"]}
    assert [c["chunk_id"] for c in second["chunks"]] == [c["chunk_id"] for c in again["chunks"]]


def test_a_disabled_chunk_is_absent_from_the_results(ingress: httpx.Client, owner: Account, planted: SimpleNamespace) -> None:
    before = hits_of(ingress, owner, planted, keyword_question(), vector_similarity_weight=0, similarity_threshold=0)
    target = next(c for c in before if FIRST.token in c["content"])
    path = f"/api/v1/datasets/{planted.dataset_id}/documents/{planted.doc_id}/chunks/{target['chunk_id']}"
    try:
        ok(api(ingress, "PATCH", path, owner.token, body={"available": False}))
        after = hits_of(ingress, owner, planted, keyword_question(), vector_similarity_weight=0, similarity_threshold=0)
        assert target["chunk_id"] not in {c["chunk_id"] for c in after}
    finally:
        ok(api(ingress, "PATCH", path, owner.token, body={"available": True}))
    restored = hits_of(ingress, owner, planted, keyword_question(), vector_similarity_weight=0, similarity_threshold=0)
    assert target["chunk_id"] in {c["chunk_id"] for c in restored}


def test_one_call_spends_exactly_one_embedding_request_and_leaks_no_key(ingress: httpx.Client, owner: Account, planted: SimpleNamespace, fake: FakeProvider) -> None:
    before = len(fake.hits(EMBEDDINGS))
    resp = search(ingress, owner, [planted.dataset_id], FIRST.question)
    assert resp.status_code == 200
    assert len(fake.hits(EMBEDDINGS)) - before == 1
    assert KEY_ONE not in resp.text and "api_key" not in resp.text


# ----------------------------------------------------------------------------- isolation


def test_a_non_member_a_foreign_dataset_and_a_random_id_all_answer_the_same_404(
    ingress: httpx.Client, registry: AccountRegistry, owner: Account, planted: SimpleNamespace, fake: FakeProvider
) -> None:
    stranger = workspace(ingress, registry, fake, "retrx")
    before = len(fake.hits(EMBEDDINGS))
    non_member = search(ingress, stranger, [planted.dataset_id], "anything", tenant_id=owner.tenant_id)
    foreign = search(ingress, stranger, [planted.dataset_id], "anything")
    random = search(ingress, stranger, ["a" * 32], "anything")
    own_but_mixed = search(ingress, owner, [planted.dataset_id, "b" * 32], "anything")
    assert [r.status_code for r in (non_member, foreign, random, own_but_mixed)] == [404, 404, 404, 404]
    assert non_member.content == foreign.content == random.content == own_but_mixed.content
    assert non_member.json() == NOT_FOUND
    assert len(fake.hits(EMBEDDINGS)) == before, "a refused request never reaches the provider"


def test_a_teammate_cannot_search_a_private_dataset(ingress: httpx.Client, registry: AccountRegistry, owner: Account, planted: SimpleNamespace) -> None:
    mate = registry.register(prefix="retrm")
    join(ingress, owner, mate)
    resp = search(ingress, mate, [planted.dataset_id], "anything", tenant_id=owner.tenant_id)
    assert resp.status_code == 404 and resp.json() == NOT_FOUND


# ----------------------------------------------------------------------------- request checks


def test_a_bad_body_is_a_400_with_a_reason(ingress: httpx.Client, owner: Account, planted: SimpleNamespace) -> None:
    ids = [planted.dataset_id]
    unknown = api(ingress, "POST", SEARCH, owner.token, body={"dataset_ids": ids, "question": "q", "rerank": True})
    assert unknown.status_code == 400
    for body, reason in (
        ({"dataset_ids": ids, "question": "   "}, "question_invalid"),
        ({"dataset_ids": [], "question": "q"}, "fields_invalid"),
        ({"dataset_ids": ids, "question": "q", "similarity_threshold": 2}, "fields_invalid"),
        ({"dataset_ids": ids, "question": "q", "size": 101}, "fields_invalid"),
        ({"dataset_ids": ids, "question": "q", "fusion": "bm25"}, "fields_invalid"),
    ):
        resp = api(ingress, "POST", SEARCH, owner.token, body=body)
        assert resp.status_code == 400 and resp.json()["data"]["reason"] == reason, (body, resp.text)


def test_the_route_needs_a_credential(ingress: httpx.Client, planted: SimpleNamespace) -> None:
    ingress.cookies.clear()
    resp = ingress.post(SEARCH, json={"dataset_ids": [planted.dataset_id], "question": "q"}, headers=_bearer("not-a-token"))
    assert resp.status_code == 401
