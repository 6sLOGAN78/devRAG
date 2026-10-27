"""Cited chat completions through the running stack and the loopback provider."""
from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from types import SimpleNamespace

import httpx
import pytest
import valkey

from test.helpers.accounts import Account, AccountRegistry, unique_name
from test.helpers.fake_provider import FakeProvider, running_stack_fake_provider
from test.helpers.planted import FACTS, off_topic_question
from test.testcases.conftest import BASE_URL
from test.testcases.test_chat_assistant_flow import MODEL
from test.testcases.test_dataset_flow import create, workspace
from test.testcases.test_provider_flow import api, join, ok, sql
from test.testcases.test_retrieval_flow import make_planted, search

pytestmark = pytest.mark.e2e
COMPLETIONS = "/api/v1/chat/completions"


@pytest.fixture(scope="module")
def fake() -> Iterator[FakeProvider]:
    with running_stack_fake_provider() as provider:
        provider.chat_mode = "marker"
        yield provider


@pytest.fixture(scope="module")
def registry() -> Iterator[AccountRegistry]:
    accounts = AccountRegistry(BASE_URL)
    try:
        yield accounts
    finally:
        accounts.cleanup()


@pytest.fixture(scope="module")
def world(ingress: httpx.Client, registry: AccountRegistry, fake: FakeProvider) -> SimpleNamespace:
    owner = workspace(ingress, registry, fake, "turn")
    planted = make_planted(ingress, owner)
    return SimpleNamespace(owner=owner, planted=planted)


def assistant(ingress: httpx.Client, who: Account, *, dataset_ids: list[str] | None = None, **extra: object) -> dict:
    body = {"name": unique_name("turn"), "llm_id": MODEL, "kb_ids": dataset_ids or [], **extra}
    return ok(api(ingress, "POST", "/api/v1/chats", who.token, body=body))


def ask(ingress: httpx.Client, who: Account, chat_id: str, message: str, **extra: object) -> httpx.Response:
    return api(ingress, "POST", COMPLETIONS, who.token, body={"chat_id": chat_id, "message": message, "stream": False, **extra})


def test_cited_answer_matches_first_retrieval_hit_and_persists(ingress: httpx.Client, world: SimpleNamespace, fake: FakeProvider) -> None:
    fake.reset()
    chat = assistant(ingress, world.owner, dataset_ids=[world.planted.dataset_id], vector_similarity_weight=0, similarity_threshold=0)
    answer = ok(ask(ingress, world.owner, chat["id"], FACTS[0].question))
    first = ok(search(ingress, world.owner, [world.planted.dataset_id], FACTS[0].question, vector_similarity_weight=0, similarity_threshold=0))["chunks"][0]
    assert "##0$$" in answer["answer"]
    assert answer["reference"]["chunks"][0]["chunk_id"] == first["chunk_id"]
    assert FACTS[0].token in answer["reference"]["chunks"][0]["content"]
    assert answer["finish"] == "complete" and answer["usage"]["total"] > 0 and answer["latency_ms"] >= 0
    assert answer["final"] is True and answer["empty"] is False and len(fake.chat_requests()) == 1
    session = ok(api(ingress, "GET", f"/api/v1/chats/{chat['id']}/sessions/{answer['session_id']}", world.owner.token))
    assert [item["role"] for item in session["messages"]] == ["user", "assistant"]
    assert session["messages"][1]["reference"] == answer["reference"]


def test_second_turn_uses_history_without_old_markers(ingress: httpx.Client, world: SimpleNamespace, fake: FakeProvider) -> None:
    fake.reset()
    chat = assistant(ingress, world.owner)
    first = ok(ask(ingress, world.owner, chat["id"], "First question"))
    second = ok(ask(ingress, world.owner, chat["id"], "Second question", session_id=first["session_id"]))
    history = fake.chat_requests()[-1]["messages"]
    assert second["session_id"] == first["session_id"] and len(history) >= 3
    assert history[-3]["content"] == "First question" and history[-1]["content"] == "Second question"
    assert "##" not in history[-2]["content"]


def test_empty_retrieval_makes_no_model_call(ingress: httpx.Client, world: SimpleNamespace, fake: FakeProvider) -> None:
    fake.reset()
    chat = assistant(ingress, world.owner, dataset_ids=[world.planted.dataset_id], vector_similarity_weight=0, similarity_threshold=0.2)
    final = ok(ask(ingress, world.owner, chat["id"], off_topic_question()))
    assert final["answer"] == chat["prompt_config"]["empty_response"]
    assert final["empty"] is True and final["reference"]["chunks"] == [] and fake.chat_requests() == []


def test_keyword_still_answers_with_zero_vector_weight(ingress: httpx.Client, world: SimpleNamespace, fake: FakeProvider) -> None:
    fake.reset()
    chat = assistant(ingress, world.owner, dataset_ids=[world.planted.dataset_id], vector_similarity_weight=0, similarity_threshold=0.2)
    final = ok(ask(ingress, world.owner, chat["id"], FACTS[0].question))
    assert final["empty"] is False and len(fake.chat_requests()) == 1


def test_plain_chat_has_no_embedding_or_reference(ingress: httpx.Client, world: SimpleNamespace, fake: FakeProvider) -> None:
    fake.reset()
    chat = assistant(ingress, world.owner)
    final = ok(ask(ingress, world.owner, chat["id"], "Hello there"))
    assert final["empty"] is False and final["reference"]["chunks"] == []
    assert fake.hits("/v1/embeddings") == [] and len(fake.chat_requests()) == 1


@pytest.mark.parametrize("message", ["", "   ", "x" * 8001])
def test_invalid_question_is_400_before_provider(ingress: httpx.Client, world: SimpleNamespace, fake: FakeProvider, message: str) -> None:
    fake.reset()
    chat = assistant(ingress, world.owner)
    response = ask(ingress, world.owner, chat["id"], message)
    assert response.status_code == 400 and response.json()["data"]["reason"] == "question_invalid"
    assert fake.chat_requests() == []


def test_stream_returns_deltas_final_and_done(ingress: httpx.Client, world: SimpleNamespace, fake: FakeProvider) -> None:
    chat = assistant(ingress, world.owner)
    fake.chat_mode = "plain"
    try:
        response = api(ingress, "POST", COMPLETIONS, world.owner.token, body={"chat_id": chat["id"], "message": "hello", "stream": True})
    finally:
        fake.chat_mode = "marker"
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert "content-length" not in response.headers
    frames = [line[6:] for line in response.text.splitlines() if line.startswith("data: ")]
    assert frames[-1] == "[DONE]"
    views = [json.loads(raw) for raw in frames[:-1]]
    assert len(views) >= 2 and all(view["code"] == 0 for view in views)
    deltas, final = views[:-1], views[-1]["data"]
    assert all(view["data"]["final"] is False and view["data"]["reference"] is None for view in deltas)
    assert final["final"] is True and final["finish"] == "complete"
    assert final["answer"] == "".join(view["data"]["answer"] for view in deltas)
    saved = ok(api(ingress, "GET", f"/api/v1/chats/{chat['id']}/sessions/{final['session_id']}", world.owner.token))
    assert saved["messages"][-1]["content"] == final["answer"]


def test_split_citation_marker_is_canonical_in_final_frame(ingress: httpx.Client, world: SimpleNamespace, fake: FakeProvider) -> None:
    chat = assistant(ingress, world.owner, dataset_ids=[world.planted.dataset_id], vector_similarity_weight=0, similarity_threshold=0)
    fake.chat_mode = "split_marker"
    try:
        response = api(ingress, "POST", COMPLETIONS, world.owner.token, body={"chat_id": chat["id"], "message": FACTS[0].question, "stream": True})
    finally:
        fake.chat_mode = "marker"
    assert response.status_code == 200
    views = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: {")]
    deltas = [view["data"]["answer"] for view in views[:-1]]
    assert "##" in deltas and "1$$" in deltas
    assert views[-1]["data"]["final"] is True
    assert "##1$$" in views[-1]["data"]["answer"]


def test_midstream_failure_frame(ingress: httpx.Client, world: SimpleNamespace, fake: FakeProvider) -> None:
    chat = assistant(ingress, world.owner)
    fake.chat_mode = "error_midstream"
    try:
        response = api(ingress, "POST", COMPLETIONS, world.owner.token, body={"chat_id": chat["id"], "message": "hello", "stream": True})
    finally:
        fake.chat_mode = "marker"
    assert response.status_code == 200
    frames = [line[6:] for line in response.text.splitlines() if line.startswith("data: ")]
    assert frames[-1] == "[DONE]"
    views = [json.loads(raw) for raw in frames[:-1]]
    assert any(view["code"] == 0 and view["data"]["final"] is False for view in views)
    failure = views[-1]
    assert failure["code"] != 0 and failure["data"]["final"] is True
    assert failure["data"]["reason"] == "provider_unreachable"
    saved = ok(api(ingress, "GET", f"/api/v1/chats/{chat['id']}/sessions/{failure['data']['session_id']}", world.owner.token))
    assert saved["messages"][-1]["finish"] == "failed"


@pytest.mark.parametrize(
    ("change", "status", "reason"),
    [
        ({"message": ""}, 400, "question_invalid"),
        ({"message": "   "}, 400, "question_invalid"),
        ({"message": "x" * 8001}, 400, "question_invalid"),
        ({"chat_id": "0" * 32}, 404, None),
        ({"tenant_id": "0" * 32}, 404, None),
        ({"api_key": "never-accepted"}, 400, None),
        ({"chat_id": "bad"}, 400, None),
    ],
)
def test_stream_prebyte_refusals_keep_http_status(
    ingress: httpx.Client, world: SimpleNamespace, fake: FakeProvider, change: dict, status: int, reason: str | None,
) -> None:
    chat = assistant(ingress, world.owner)
    fake.reset()
    response = api(ingress, "POST", COMPLETIONS, world.owner.token,
                   body={"chat_id": chat["id"], "message": "hello", "stream": True, **change})
    assert response.status_code == status and response.headers["content-type"].startswith("application/json")
    if reason:
        assert response.json()["data"]["reason"] == reason
    assert fake.chat_requests() == []


def test_absent_chat_is_the_one_404(ingress: httpx.Client, world: SimpleNamespace) -> None:
    assert ask(ingress, world.owner, uuid.uuid4().hex, "hello").status_code == 404


def test_foreign_session_is_the_one_404(ingress: httpx.Client, world: SimpleNamespace, registry: AccountRegistry) -> None:
    other = registry.register(prefix="turnother")
    chat = assistant(ingress, world.owner)
    session = ok(api(ingress, "POST", f"/api/v1/chats/{chat['id']}/sessions", world.owner.token, body={}))
    assert ask(ingress, other, chat["id"], "hello", session_id=session["id"]).status_code == 404


def test_preheld_turn_lock_refuses_second_turn(ingress: httpx.Client, world: SimpleNamespace) -> None:
    chat = assistant(ingress, world.owner)
    session = ok(api(ingress, "POST", f"/api/v1/chats/{chat['id']}/sessions", world.owner.token, body={}))
    from common.settings import load_settings

    cfg = load_settings().redis
    client = valkey.Valkey(host=cfg.host, port=cfg.port, password=cfg.password or None, db=cfg.db)
    key = f"chat_turn:{session['id']}"
    try:
        assert client.set(key, b"held", nx=True, ex=30)
        response = ask(ingress, world.owner, chat["id"], "hello", session_id=session["id"])
        assert response.status_code == 409 and response.json()["data"]["reason"] == "turn_in_progress"
    finally:
        client.delete(key)
        client.close()


def test_tenant_mismatch_is_not_found(ingress: httpx.Client, world: SimpleNamespace) -> None:
    chat = assistant(ingress, world.owner)
    assert ask(ingress, world.owner, chat["id"], "hello", tenant_id=uuid.uuid4().hex).status_code == 404


def test_session_is_capped_before_provider(ingress: httpx.Client, world: SimpleNamespace, fake: FakeProvider) -> None:
    fake.reset()
    chat = assistant(ingress, world.owner)
    session = ok(api(ingress, "POST", f"/api/v1/chats/{chat['id']}/sessions", world.owner.token, body={}))
    from common.settings import load_settings

    cap = load_settings().chat.max_session_messages
    messages = [{"id": uuid.uuid4().hex, "role": "user", "content": "old"} for _ in range(cap)]
    import json

    sql("UPDATE `conversation` SET `message` = %s WHERE `id` = %s", (json.dumps(messages), session["id"]))
    response = ask(ingress, world.owner, chat["id"], "hello", session_id=session["id"])
    assert response.status_code == 409 and response.json()["data"]["reason"] == "session_full"
    assert fake.chat_requests() == []


def test_bound_but_unavailable_dataset_stores_no_question(ingress: httpx.Client, world: SimpleNamespace, registry: AccountRegistry, fake: FakeProvider) -> None:
    fake.reset()
    member = registry.register(prefix="turnmember")
    join(ingress, world.owner, member)
    dataset_id = ok(create(ingress, world.owner, permission="team"))["id"]
    chat = assistant(ingress, world.owner, dataset_ids=[dataset_id], permission="team")
    ok(api(ingress, "PUT", f"/api/v1/datasets/{dataset_id}", world.owner.token, body={"permission": "me"}))
    response = ask(ingress, member, chat["id"], "hello")
    assert response.status_code == 409 and response.json()["data"]["reason"] == "datasets_unavailable"
    sessions = ok(api(ingress, "GET", f"/api/v1/chats/{chat['id']}/sessions", member.token))
    assert sessions["total"] == 0 and fake.chat_requests() == []


def test_deleted_chat_model_is_409(ingress: httpx.Client, registry: AccountRegistry, fake: FakeProvider) -> None:
    owner = workspace(ingress, registry, fake, "turnmodel")
    chat = assistant(ingress, owner)
    sql("DELETE FROM `tenant_llm` WHERE `tenant_id` = %s AND `llm_name` = %s", (owner.tenant_id, "fake-chat"))
    response = ask(ingress, owner, chat["id"], "hello")
    assert response.status_code == 409 and response.json()["data"]["reason"] == "model_unavailable"


def test_provider_failure_stores_failed_turn_and_releases_lock(ingress: httpx.Client, registry: AccountRegistry, fake: FakeProvider) -> None:
    fake.reset()
    owner = workspace(ingress, registry, fake, "turnfail")
    chat = assistant(ingress, owner)
    session = ok(api(ingress, "POST", f"/api/v1/chats/{chat['id']}/sessions", owner.token, body={}))
    fake.chat_mode = "error_midstream"
    try:
        for _ in range(2):
            response = ask(ingress, owner, chat["id"], "The failing question", session_id=session["id"])
            assert response.status_code == 502 and response.json()["data"]["reason"] == "provider_unreachable"
    finally:
        fake.chat_mode = "marker"
    saved = ok(api(ingress, "GET", f"/api/v1/chats/{chat['id']}/sessions/{session['id']}", owner.token))["messages"]
    assert [item["role"] for item in saved] == ["user", "assistant", "user", "assistant"]
    assert saved[0]["content"] == "The failing question" and saved[1]["finish"] == "failed"


@pytest.mark.parametrize("fact", FACTS, ids=[fact.token for fact in FACTS])
def test_each_planted_fact_reaches_the_chat_prompt_without_rerank(ingress, world, fake, fact):
    fake.reset()
    chat = assistant(ingress, world.owner, dataset_ids=[world.planted.dataset_id], vector_similarity_weight=0.3, similarity_threshold=0.2, top_n=6)
    final = ok(ask(ingress, world.owner, chat["id"], fact.question))
    assert any(fact.token in hit["content"] for hit in final["reference"]["chunks"])
    prompt = fake.chat_requests()[-1]["messages"][0]["content"]
    assert fact.token in prompt
