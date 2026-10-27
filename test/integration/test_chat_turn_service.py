"""The turn service against real MySQL, Valkey, Elasticsearch and a loopback model provider."""
from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Iterator
from unittest.mock import patch

import pytest

from api.db.database import DB
from api.db.models import Dialog
from api.db.services import chat_turn_service as turns
from api.db.services import conversation_service as sessions
from api.db.services import dialog_service
from api.db.services import tenant_model_service as structure
from api.db.services.service_errors import Kind, ServiceError
from api.db.services.tenant_model_service import NewModel
from rag.llm.stream import Usage
from test.helpers.accounts import AccountRegistry
from test.helpers.doc_store_contract import RARE_KEYWORD, unit_vector
from test.helpers.fake_provider import FakeProvider, running_fake_provider
from test.helpers.ingest import DIMENSION, World, cleanup_tasks, make_pipeline_world
from test.integration.test_knowledgebase_service import principal_of
from test.integration.test_retrieval_service import plant_golden, scope_of
from test.integration.test_upload_service import _bound_database  # noqa: F401
from test.testcases.conftest import BASE_URL

pytestmark = pytest.mark.integration
COMPAT = "OpenAI-API-Compatible"
CHAT_ID = f"fake-chat@{COMPAT}"


@pytest.fixture(scope="module")
def registry() -> Iterator[AccountRegistry]:
    accounts = AccountRegistry(BASE_URL)
    try:
        yield accounts
    finally:
        cleanup_tasks(accounts)
        accounts.cleanup()


@pytest.fixture(scope="module")
def fake() -> Iterator[FakeProvider]:
    with running_fake_provider() as provider:
        provider.chat_mode = "marker"
        yield provider


@pytest.fixture(scope="module")
def world(registry: AccountRegistry, fake: FakeProvider) -> Iterator[World]:
    made = make_pipeline_world(registry, fake)
    structure.save_instance(
        made.settings.llm, made.owner.tenant_id, COMPAT, "default", api_key=made.api_key, api_base=fake.base_url,
        api_version=None,
        models=[NewModel("fake-embed", "embedding", DIMENSION, 8192), NewModel("fake-chat", "chat", None, 8192), NewModel("fake-500", "chat", None, 8192)],
        replace_key=True,
    )
    plant_golden(made)
    made.embed_settings = dataclasses.replace(made.embed_settings, redis=made.settings.redis, es=made.settings.es)
    # The loopback provider is the intentional test endpoint; keep real Valkey on its host port.
    with patch("api.db.services.tenant_llm_service.internal_hosts", return_value=[]):
        yield made


def new_chat(world: World, *, bound: bool = True, llm_id: str = CHAT_ID, **extra: object) -> str:
    body = {
        "name": f"turn-{uuid.uuid4().hex[:12]}", "llm_id": llm_id,
        "kb_ids": [world.dataset.id] if bound else [],
        "vector_similarity_weight": 0, "similarity_threshold": 0.2,
        **extra,
    }
    return dialog_service.create_assistant(principal_of(world.owner), scope_of(world), body)["id"]


def prepare(world: World, chat_id: str, message: str = RARE_KEYWORD, **extra: object) -> turns.TurnPlan:
    return turns.prepare_turn(world.embed_settings, principal_of(world.owner), {"chat_id": chat_id, "message": message, **extra})


def complete(world: World, chat_id: str, message: str = RARE_KEYWORD, **extra: object) -> dict:
    return turns.complete_turn(world.embed_settings, principal_of(world.owner), {"chat_id": chat_id, "message": message, **extra})


def stored(world: World, chat_id: str, session_id: str) -> list[dict]:
    return sessions.get_session(principal_of(world.owner), chat_id, session_id)["messages"]


def refused(call, reason: str) -> ServiceError:
    with pytest.raises(ServiceError) as caught:
        call()
    assert caught.value.reason == reason
    return caught.value


def test_marker_maps_to_top_chunk_and_is_stored(world: World, fake: FakeProvider) -> None:
    fake.reset()
    chat = new_chat(world)
    final = complete(world, chat)
    assert "##0$$" in final["answer"] and final["reference"]["chunks"][0]["index"] == 0
    assert RARE_KEYWORD in final["reference"]["chunks"][0]["content"]
    assert final["usage"]["total"] > 0 and final["finish"] == "complete"
    assert [item["role"] for item in stored(world, chat, final["session_id"])] == ["user", "assistant"]


def test_empty_retrieval_makes_no_model_call(world: World, fake: FakeProvider) -> None:
    fake.reset()
    chat = new_chat(world, similarity_threshold=0.2)
    final = complete(world, chat, "volcanoes erupted in Iceland")
    assert final["empty"] is True and final["reference"]["chunks"] == [] and fake.chat_requests() == []


def test_plain_chat_uses_no_retrieval(world: World, fake: FakeProvider) -> None:
    fake.reset()
    chat = new_chat(world, bound=False)
    final = complete(world, chat, "hello")
    assert final["empty"] is False and final["reference"]["chunks"] == []
    assert fake.hits("/v1/embeddings") == [] and len(fake.chat_requests()) == 1


@pytest.mark.parametrize("message", ["", "   ", "x" * 8001])
def test_invalid_question_stops_before_session(world: World, message: str) -> None:
    chat = new_chat(world)
    error = refused(lambda: prepare(world, chat, message), "question_invalid")
    assert error.kind is Kind.INVALID and sessions.list_sessions(principal_of(world.owner), chat)["total"] == 0


def test_datasets_unavailable_stores_nothing(world: World) -> None:
    chat = new_chat(world, bound=False)
    with DB.connection_context():
        Dialog.update(kb_ids=[uuid.uuid4().hex]).where(Dialog.id == chat).execute()
    error = refused(lambda: prepare(world, chat), "datasets_unavailable")
    assert error.kind is Kind.CONFLICT and sessions.list_sessions(principal_of(world.owner), chat)["total"] == 0


def test_second_prepare_is_turn_in_progress(world: World) -> None:
    chat = new_chat(world, bound=False)
    plan = prepare(world, chat, "first")
    try:
        error = refused(lambda: prepare(world, chat, "second", session_id=plan.session_id), "turn_in_progress")
        assert error.kind is Kind.CONFLICT
    finally:
        turns.persist_partial(plan, "stopped")


def test_success_releases_turn_lock(world: World) -> None:
    chat = new_chat(world, bound=False)
    first = complete(world, chat, "first")
    second = complete(world, chat, "second", session_id=first["session_id"])
    assert first["session_id"] == second["session_id"]


def test_retrieval_failure_releases_lock(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    chat = new_chat(world)
    session = sessions.create_session(principal_of(world.owner), chat)["id"]

    def broken(*_: object) -> None:
        raise ServiceError(Kind.UNAVAILABLE, "index_unavailable", "index unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(turns.retrieval_service, "retrieve_for_chat", broken)
        refused(lambda: prepare(world, chat, session_id=session), "index_unavailable")
    lock = sessions.acquire_turn(world.embed_settings, session)
    assert lock.release()


def test_provider_failure_stores_failed_message_and_releases_lock(world: World) -> None:
    chat = new_chat(world, bound=False, llm_id=f"fake-500@{COMPAT}")
    session = sessions.create_session(principal_of(world.owner), chat)["id"]
    refused(lambda: complete(world, chat, "question", session_id=session), "provider_unreachable")
    assert [item["role"] for item in stored(world, chat, session)] == ["user", "assistant"]
    assert stored(world, chat, session)[1]["finish"] == "failed"
    lock = sessions.acquire_turn(world.embed_settings, session)
    assert lock.release()


def test_persist_partial_is_stopped_with_estimated_usage(world: World) -> None:
    chat = new_chat(world)
    plan = prepare(world, chat)
    turns.persist_partial(plan, "Part ##0$$")
    answer = stored(world, chat, plan.session_id)[1]
    assert answer["finish"] == "stopped" and answer["usage"]["estimated"] is True
    assert [chunk["index"] for chunk in answer["reference"]["chunks"]] == [0]


def test_persist_complete_is_idempotent(world: World) -> None:
    chat = new_chat(world, bound=False)
    plan = prepare(world, chat, "hello")
    final = turns.finalise(plan, "answer", Usage(1, 2, 3))
    turns.persist_complete(plan, final)
    turns.persist_complete(plan, final)
    assert [item["role"] for item in stored(world, chat, plan.session_id)] == ["user", "assistant"]


def test_persist_failed_is_idempotent(world: World) -> None:
    chat = new_chat(world, bound=False)
    plan = prepare(world, chat, "hello")
    turns.persist_failed(plan)
    turns.persist_failed(plan)
    assert len(stored(world, chat, plan.session_id)) == 2


def test_fallback_inserts_marker_with_injected_embedder(world: World) -> None:
    chat = new_chat(world)
    plan = prepare(world, chat)

    class MatchingEmbedder:
        expected_dimension = DIMENSION

        def encode(self, sentences: list[str]) -> tuple[list[list[float]], int]:
            return [unit_vector(1) for _ in sentences], len(sentences)

    injected = dataclasses.replace(plan, used_embedder=MatchingEmbedder())
    try:
        final = turns.finalise(injected, "Uncited sentence.", Usage(1, 2, 3))
        assert "##0$$" in final.answer and final.usage["citations"] == "inserted"
    finally:
        turns.persist_partial(plan, "stopped")


def test_history_strips_prior_markers(world: World, fake: FakeProvider) -> None:
    fake.reset()
    chat = new_chat(world, bound=False)
    first = complete(world, chat, "first")
    complete(world, chat, "second", session_id=first["session_id"])
    messages = fake.chat_requests()[-1]["messages"]
    assert messages[-3]["content"] == "first" and messages[-1]["content"] == "second"
    assert "##" not in messages[-2]["content"]


def test_question_is_stored_before_a_retrieval_error(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    chat = new_chat(world)
    session = sessions.create_session(principal_of(world.owner), chat)["id"]
    with monkeypatch.context() as patch:
        patch.setattr(turns.retrieval_service, "retrieve_for_chat", lambda *_a, **_kw: (_ for _ in ()).throw(ServiceError(Kind.UNAVAILABLE, "index_unavailable", "index unavailable")))
        refused(lambda: prepare(world, chat, "saved question", session_id=session), "index_unavailable")
    assert stored(world, chat, session)[0]["content"] == "saved question"


def test_session_cap_refuses_before_provider_and_releases_lock(world: World, fake: FakeProvider) -> None:
    chat = new_chat(world, bound=False)
    session = sessions.create_session(principal_of(world.owner), chat)["id"]
    sessions.append_user_message(principal_of(world.owner), chat, session, "old one", world.embed_settings.chat)
    sessions.append_user_message(principal_of(world.owner), chat, session, "old two", world.embed_settings.chat)
    limited = dataclasses.replace(world.embed_settings, chat=dataclasses.replace(world.embed_settings.chat, max_session_messages=2))
    fake.reset()
    error = refused(lambda: turns.prepare_turn(limited, principal_of(world.owner), {"chat_id": chat, "session_id": session, "message": "new"}), "session_full")
    assert error.kind is Kind.CONFLICT and fake.chat_requests() == []
    lock = sessions.acquire_turn(world.embed_settings, session)
    assert lock.release()
