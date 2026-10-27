"""Retrieval test end to end through Nginx on the running stack (plan 05-04; RETR-16..18, RETR-23, KB-18, TEN-03, E2E-07 API half, D-19, D-20).

Nothing of devRag is replaced: Nginx, the app, the task executor, MySQL, MinIO, Valkey and Elasticsearch are the running stack. The loopback provider is the
third party's end of the embedding wire. It answers near-identical vectors, so these tests prove the arithmetic of the three scores and the filters
(threshold, documents, switches, pages, isolation); the order change between weights with real meaning is proved with planted vectors in
``test/integration/test_retrieval_es.py`` and in the live tier.
"""
from __future__ import annotations

import subprocess
from collections.abc import Iterator
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from test.helpers.accounts import Account, AccountRegistry
from test.helpers.fake_provider import FakeProvider, running_stack_fake_provider
from test.helpers.ingest import start_parse, upload_text, wait_run
from test.helpers.planted import FACTS, planted_txt
from test.testcases.conftest import BASE_URL, PROJECT
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


def make_planted(ingress: httpx.Client, who: Account) -> SimpleNamespace:
    """A dataset holding the planted TXT (six paragraphs, six chunks), parsed and finished."""
    dataset_id = ok(create(ingress, who))["id"]
    doc = upload_text(ingress, who, dataset_id, planted_txt(), "planted.txt")
    assert start_parse(ingress, who, dataset_id, [doc["id"]]).status_code == 200
    row = wait_run(ingress, who, dataset_id, doc["id"], "3", timeout=180)
    assert row["chunk_count"] == len(FACTS)
    return SimpleNamespace(dataset_id=dataset_id, doc_id=doc["id"])


@pytest.fixture(scope="module")
def planted(ingress: httpx.Client, owner: Account) -> SimpleNamespace:
    return make_planted(ingress, owner)


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


# ----------------------------------------------------------------------------- the optional rerank stage (plan 05-05; RETR-11, RETR-12, D-03, R-197)

RERANK_PATH = "/api/v1/rerank"
RERANK_ID = "fake-rerank@OpenRouter"
CANDIDATE_CAP = 16  # measured retrieval.rerank_max_candidates (R-219)


STRANGER_RERANK_ID = "stranger-rerank@OpenRouter"


def save_rerank_model(ingress: httpx.Client, who: Account, fake: FakeProvider, name: str = "fake-rerank") -> None:
    body = {"provider": "OpenRouter", "api_key": KEY_ONE, "base_url": f"{fake.stack_root}/api/v1", "models": [{"name": name, "type": "rerank"}]}
    ok(api(ingress, "PUT", "/api/v1/providers", who.token, body=body))


@pytest.fixture(scope="module")
def ranker(ingress: httpx.Client, registry: AccountRegistry, fake: FakeProvider) -> Account:
    """Its own workspace, so the rerank cases do not spend the shared retrieval-test budget (30 per 60 s per workspace and user)."""
    who = workspace(ingress, registry, fake, "retrk")
    save_rerank_model(ingress, who, fake)
    return who


@pytest.fixture(scope="module")
def ranked(ingress: httpx.Client, ranker: Account) -> SimpleNamespace:
    return make_planted(ingress, ranker)


def rerank_calls(fake: FakeProvider) -> list[Any]:
    return fake.hits(RERANK_PATH)


def test_a_rerank_model_changes_the_first_hit_and_reports_it(ingress: httpx.Client, ranker: Account, ranked: SimpleNamespace, fake: FakeProvider) -> None:
    plain = hits_of(ingress, ranker, ranked, FIRST.token, vector_similarity_weight=1, similarity_threshold=0)
    target = next(f for f in FACTS if f.token in plain[-1]["content"])  # the chunk the vector order puts last
    assert target.token not in plain[0]["content"]
    before = len(rerank_calls(fake))

    view = ok(search(ingress, ranker, [ranked.dataset_id], target.token, vector_similarity_weight=1, similarity_threshold=0, rerank_id=RERANK_ID))
    assert view["rerank_applied"] is True and view["timings"]["rerank_ms"] > 0
    assert target.token in view["chunks"][0]["content"], "the rerank order differs from the fusion order"
    assert view["chunks"][0]["rerank_similarity"] == pytest.approx(1.0) and all("rerank_similarity" in c for c in view["chunks"])
    calls = rerank_calls(fake)[before:]
    assert len(calls) == 1, "exactly one rerank request per reranked call"
    assert len(calls[0].body["documents"]) <= CANDIDATE_CAP and calls[0].body["model"] == "fake-rerank"
    assert KEY_ONE not in str(view)

    unranked = ok(search(ingress, ranker, [ranked.dataset_id], target.token, vector_similarity_weight=1, similarity_threshold=0))
    assert unranked["rerank_applied"] is False and target.token not in unranked["chunks"][0]["content"]
    assert all("rerank_similarity" not in c for c in unranked["chunks"])
    assert len(rerank_calls(fake)) == before + 1, "a call without rerank_id makes no rerank request"


def test_a_failing_rerank_model_is_a_502_with_the_reason_and_no_chunks(ingress: httpx.Client, ranker: Account, ranked: SimpleNamespace, fake: FakeProvider) -> None:
    fake.rerank_mode = "fail"
    try:
        resp = search(ingress, ranker, [ranked.dataset_id], FIRST.token, similarity_threshold=0, rerank_id=RERANK_ID)
    finally:
        fake.rerank_mode = "ok"
    body = resp.json()
    assert resp.status_code == 502 and body["code"] != 0 and body["data"]["reason"] == "rerank_unavailable", resp.text
    assert not body["data"].get("chunks") and KEY_ONE not in resp.text and fake.stack_root not in resp.text
    assert ingress.get("/v1/user/info", headers=_bearer(ranker.token)).status_code == 200, "a rerank failure never ends the session"


def test_an_unknown_and_another_workspaces_rerank_model_are_model_unavailable(
    ingress: httpx.Client, registry: AccountRegistry, ranker: Account, ranked: SimpleNamespace, fake: FakeProvider
) -> None:
    stranger = workspace(ingress, registry, fake, "retrr")
    save_rerank_model(ingress, stranger, fake, "stranger-rerank")
    own = search(ingress, stranger, [make_planted(ingress, stranger).dataset_id], FIRST.token, rerank_id=STRANGER_RERANK_ID)
    assert own.status_code == 200 and own.json()["data"]["rerank_applied"] is True, "the model works in the workspace that owns it"
    before = len(fake.hits(EMBEDDINGS)) + len(rerank_calls(fake))
    for rerank_id in ("missing@OpenRouter", "fake-rerank@NoSuchProvider", "x" * 129, STRANGER_RERANK_ID):
        resp = search(ingress, ranker, [ranked.dataset_id], FIRST.token, rerank_id=rerank_id)
        assert resp.status_code == 409 and resp.json()["data"]["reason"] == "model_unavailable", (rerank_id, resp.text)
    assert len(fake.hits(EMBEDDINGS)) + len(rerank_calls(fake)) == before, "a refused model id spends no embedding and no rerank request"


def test_a_malformed_rerank_id_is_a_400(ingress: httpx.Client, ranker: Account, ranked: SimpleNamespace) -> None:
    for bad in (5, "", ["a"]):
        resp = search(ingress, ranker, [ranked.dataset_id], FIRST.token, rerank_id=bad)
        assert resp.status_code in (400, 422) and resp.json()["code"] != 0, (bad, resp.text)


def test_real_tei_rerank_through_the_stack(ingress: httpx.Client, registry: AccountRegistry, fake: FakeProvider) -> None:
    who = workspace(ingress, registry, fake, "realtei")
    model = "BAAI/bge-reranker-base"
    ok(api(ingress, "PUT", "/api/v1/providers", who.token, body={"provider": "TEI", "models": [{"name": model, "type": "rerank"}]}))
    dataset = ok(create(ingress, who, parser_config={"chunk_token_num": 24}))["id"]
    text = (
        "capital capital France France France is a country in western Europe known for wine and cheese\n\n"
        "Paris is the seat of government of the French republic"
    )
    document = upload_text(ingress, who, dataset, text.encode(), "geography.txt")
    ok(start_parse(ingress, who, dataset, [document["id"]]))
    row = wait_run(ingress, who, dataset, document["id"], "3", timeout=180)
    assert row["chunk_count"] == 2
    since = datetime.now(timezone.utc).isoformat()
    view = ok(search(ingress, who, [dataset], "What is the capital of France?", similarity_threshold=0, vector_similarity_weight=0.8, rerank_id=f"{model}@TEI"))
    assert view["rerank_applied"] is True
    assert len(view["chunks"]) == 2
    assert all("rerank_similarity" in hit for hit in view["chunks"])
    assert "Paris" in view["chunks"][0]["content"]
    assert view["chunks"][0]["rerank_similarity"] > view["chunks"][1]["rerank_similarity"]
    result = subprocess.run(["docker", "logs", "--since", since, f"{PROJECT}-tei-1"], capture_output=True, text=True, check=True, timeout=30)
    assert "rerank" in (result.stdout + result.stderr).lower(), "real TEI logs must show this rerank request"
