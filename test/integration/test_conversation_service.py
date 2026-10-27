"""Session persistence and turn guards against the running MySQL and Valkey stack (plan 05-09)."""
# ruff: noqa: F401, F811 -- imported fixtures are discovered by pytest and shadowed by test parameters.
from __future__ import annotations

import dataclasses
import threading
import uuid

import pytest

from api.db.database import DB
from api.db.models import Conversation, Dialog
from api.db.services import conversation_service as svc
from api.db.services.service_errors import Kind, ServiceError
from common.settings import ChatSettings, RedisSettings, load_settings
from test.helpers.db import root_connection
from test.helpers.wait import wait_until
from test.integration.test_dialog_service import _bound_database, create, dataset, llm, registry, set_permission, world

pytestmark = pytest.mark.integration


def test_own_session_and_teammate_isolation(world):
    chat = create(world, world.a, permission="team")
    mine = svc.create_session(world.principal(world.a), chat["id"])
    assert mine["chat_id"] == chat["id"] and mine["messages"] == []
    assert [row["id"] for row in svc.list_sessions(world.principal(world.a), chat["id"], 1, 20)["items"]] == [mine["id"]]
    assert svc.list_sessions(world.principal(world.b), chat["id"], 1, 20)["items"] == []
    with pytest.raises(ServiceError) as err:
        svc.get_session(world.principal(world.b), chat["id"], mine["id"])
    assert err.value.kind == Kind.NOT_FOUND


def test_turn_lock_has_ttl_and_contention(world):
    sid = uuid.uuid4().hex
    settings = load_settings()
    lock = svc.acquire_turn(settings, sid)
    try:
        assert lock.ttl() > 0
        with pytest.raises(ServiceError) as err:
            svc.acquire_turn(settings, sid)
        assert err.value.reason == "turn_in_progress"
    finally:
        lock.release()
    again = svc.acquire_turn(settings, sid)
    again.release()


def test_lost_turn_lock_cannot_release_new_owner(world):
    sid = uuid.uuid4().hex
    settings = load_settings()
    old = svc.acquire_turn(settings, sid)
    old._client.delete(old.key)  # simulate expiry before the first owner's cleanup
    new = svc.acquire_turn(settings, sid)
    try:
        assert old.release() is False
        assert new.ttl() > 0
    finally:
        new.release()


def test_renewal_resets_the_owners_lease(world):
    settings = load_settings()
    lock = svc.acquire_turn(settings, uuid.uuid4().hex)
    try:
        lock._client.expire(lock.key, 1)
        lock.renew()
        assert lock.ttl() >= settings.chat.stream_deadline_seconds + 29
    finally:
        lock.release()


def test_lost_turn_cannot_renew_the_new_owners_lease(world):
    settings = load_settings()
    sid = uuid.uuid4().hex
    old = svc.acquire_turn(settings, sid)
    old._client.delete(old.key)
    new = svc.acquire_turn(settings, sid)
    try:
        with pytest.raises(ServiceError) as err:
            old.renew()
        assert err.value.reason == "turn_in_progress"
        assert new.ttl() > 0
        assert old.release() is False
    finally:
        new.release()


def test_store_outage_fails_closed():
    settings = load_settings()
    broken = dataclasses.replace(settings, redis=RedisSettings("127.0.0.1", 1, "", 0))
    with pytest.raises(ServiceError) as err:
        svc.acquire_turn(broken, uuid.uuid4().hex)
    assert err.value.kind == Kind.UNAVAILABLE
    with pytest.raises(ServiceError) as err:
        svc.chat_rate_guard(broken, uuid.uuid4().hex, uuid.uuid4().hex)
    assert err.value.kind == Kind.UNAVAILABLE


def test_redaction_after_dataset_flips_to_me(world):
    kb_id = dataset(world.tenant, world.a, "team")
    chat = create(world, world.a, permission="team", kb_ids=[kb_id])
    session = svc.create_session(world.principal(world.b), chat["id"])
    svc.append_assistant_message(session["id"], {
        "id": uuid.uuid4().hex, "role": "assistant", "content": "answer", "created_at": "2026-10-24T00:00:00Z", "finish": "complete",
        "reference": {"chunks": [{"index": 0, "dataset_id": kb_id, "content": "private text"}], "doc_aggs": []},
    })
    assert svc.get_session(world.principal(world.b), chat["id"], session["id"])["messages"][0]["reference"]["chunks"][0]["content"] == "private text"
    set_permission(kb_id, "me")
    assert svc.get_session(world.principal(world.b), chat["id"], session["id"])["messages"][0]["reference"]["chunks"] == [{"index": 0, "unavailable": True}]


@pytest.mark.parametrize("who", ["owner", "admin", "b", "outsider"])
def test_private_assistant_session_is_invisible(world, who):
    chat = create(world, world.a)
    session = svc.create_session(world.principal(world.a), chat["id"])
    with pytest.raises(ServiceError) as err:
        svc.get_session(world.principal(getattr(world, who)), chat["id"], session["id"])
    assert err.value.kind == Kind.NOT_FOUND


def test_teammate_session_is_identical_to_absent_id(world):
    chat = create(world, world.a, permission="team")
    session = svc.create_session(world.principal(world.a), chat["id"])
    errors = []
    for sid in (session["id"], uuid.uuid4().hex):
        with pytest.raises(ServiceError) as err:
            svc.get_session(world.principal(world.b), chat["id"], sid)
        errors.append((err.value.kind, err.value.message))
    assert errors == [(Kind.NOT_FOUND, "not found")] * 2


def test_list_paginates_newest_first(world):
    chat = create(world, world.a, permission="team")
    first = svc.create_session(world.principal(world.a), chat["id"])
    second = svc.create_session(world.principal(world.a), chat["id"])
    listed = svc.list_sessions(world.principal(world.a), chat["id"], 1, 1)
    assert listed["total"] == 2 and len(listed["items"]) == 1
    assert {listed["items"][0]["id"], svc.list_sessions(world.principal(world.a), chat["id"], 2, 1)["items"][0]["id"]} == {first["id"], second["id"]}


def test_delete_only_own_session(world):
    chat = create(world, world.a, permission="team")
    session = svc.create_session(world.principal(world.a), chat["id"])
    with pytest.raises(ServiceError) as err:
        svc.delete_session(world.principal(world.b), chat["id"], session["id"])
    assert err.value.kind == Kind.NOT_FOUND
    assert svc.delete_session(world.principal(world.a), chat["id"], session["id"]) == {"deleted": session["id"]}
    with pytest.raises(ServiceError):
        svc.get_session(world.principal(world.a), chat["id"], session["id"])


def test_first_question_names_session_and_returns_prior_history(world):
    chat = create(world, world.a)
    session = svc.create_session(world.principal(world.a), chat["id"])
    mid, history = svc.append_user_message(world.principal(world.a), chat["id"], session["id"], "  First\n question  ", ChatSettings())
    assert len(mid) == 32 and history == []
    assert svc.get_session(world.principal(world.a), chat["id"], session["id"])["name"] == "First question"
    _, history = svc.append_user_message(world.principal(world.a), chat["id"], session["id"], "Another question", ChatSettings())
    assert len(history) == 1 and history[0]["id"] == mid


@pytest.mark.parametrize("question", ["", "   ", "x" * 8001])
def test_bad_question_is_rejected_without_append(world, question):
    chat = create(world, world.a)
    session = svc.create_session(world.principal(world.a), chat["id"])
    with pytest.raises(ServiceError) as err:
        svc.append_user_message(world.principal(world.a), chat["id"], session["id"], question, ChatSettings())
    assert err.value.reason == "question_invalid"
    assert svc.get_session(world.principal(world.a), chat["id"], session["id"])["messages"] == []


def test_session_message_cap(world):
    chat = create(world, world.a)
    session = svc.create_session(world.principal(world.a), chat["id"])
    settings = dataclasses.replace(ChatSettings(), max_session_messages=2)
    for _ in range(2):
        svc.append_user_message(world.principal(world.a), chat["id"], session["id"], "question", settings)
    with pytest.raises(ServiceError) as err:
        svc.append_user_message(world.principal(world.a), chat["id"], session["id"], "third", settings)
    assert err.value.reason == "session_full"


def test_append_and_replace_assistant_message(world):
    chat = create(world, world.a)
    session = svc.create_session(world.principal(world.a), chat["id"])
    mid = uuid.uuid4().hex
    svc.append_assistant_message(session["id"], {"id": mid, "role": "assistant", "content": "draft", "finish": "stopped", "created_at": "2026-10-24T00:00:00Z"})
    svc.replace_assistant_message(session["id"], mid, {"role": "assistant", "content": "final", "finish": "complete", "created_at": "2026-10-24T00:00:01Z"})
    messages = svc.get_session(world.principal(world.a), chat["id"], session["id"])["messages"]
    assert messages[0]["id"] == mid and messages[0]["content"] == "final"


@pytest.mark.parametrize("thumb", ["up", "down", None])
def test_feedback_on_completed_assistant_message(world, thumb):
    chat = create(world, world.a)
    session = svc.create_session(world.principal(world.a), chat["id"])
    mid = uuid.uuid4().hex
    svc.append_assistant_message(session["id"], {"id": mid, "role": "assistant", "content": "answer", "finish": "complete", "created_at": "2026-10-24T00:00:00Z"})
    assert svc.set_feedback(world.principal(world.a), chat["id"], session["id"], mid, thumb)["feedback"] == thumb
    assert svc.get_session(world.principal(world.a), chat["id"], session["id"])["messages"][0]["feedback"] == thumb


@pytest.mark.parametrize("role,finish", [("user", "complete"), ("assistant", "stopped"), ("assistant", "failed")])
def test_feedback_rejects_non_completed_assistant_messages(world, role, finish):
    chat = create(world, world.a)
    session = svc.create_session(world.principal(world.a), chat["id"])
    mid = uuid.uuid4().hex
    with DB.connection_context():
        Conversation.update(message=[{"id": mid, "role": role, "finish": finish, "content": "text"}]).where(Conversation.id == session["id"]).execute()
    with pytest.raises(ServiceError) as err:
        svc.set_feedback(world.principal(world.a), chat["id"], session["id"], mid, "up")
    assert err.value.kind == Kind.NOT_FOUND


def test_feedback_rejects_foreign_session(world):
    chat = create(world, world.a, permission="team")
    session = svc.create_session(world.principal(world.a), chat["id"])
    mid = uuid.uuid4().hex
    svc.append_assistant_message(session["id"], {"id": mid, "role": "assistant", "content": "answer", "finish": "complete", "created_at": "2026-10-24T00:00:00Z"})
    with pytest.raises(ServiceError) as err:
        svc.set_feedback(world.principal(world.b), chat["id"], session["id"], mid, "down")
    assert err.value.kind == Kind.NOT_FOUND


def test_message_cursor_paginates_120_in_chronological_order(world):
    chat = create(world, world.a)
    session = svc.create_session(world.principal(world.a), chat["id"])
    messages = [{"id": uuid.uuid4().hex, "role": "user", "content": str(i), "created_at": "2026-10-24T00:00:00Z"} for i in range(120)]
    with DB.connection_context():
        Conversation.update(message=messages).where(Conversation.id == session["id"]).execute()
    first = svc.get_session(world.principal(world.a), chat["id"], session["id"])
    second = svc.get_session(world.principal(world.a), chat["id"], session["id"], before=first["messages"][0]["id"])
    third = svc.get_session(world.principal(world.a), chat["id"], session["id"], before=second["messages"][0]["id"])
    assert [len(p["messages"]) for p in (first, second, third)] == [50, 50, 20]
    assert [p["has_earlier"] for p in (first, second, third)] == [True, True, False]
    assert [m["content"] for p in (third, second, first) for m in p["messages"]] == [str(i) for i in range(120)]


def test_redaction_after_dataset_is_deleted(world):
    kb_id = dataset(world.tenant, world.a, "team")
    chat = create(world, world.a, permission="team", kb_ids=[kb_id])
    session = svc.create_session(world.principal(world.b), chat["id"])
    svc.append_assistant_message(session["id"], {
        "id": uuid.uuid4().hex,
        "role": "assistant",
        "content": "answer",
        "finish": "complete",
        "created_at": "2026-10-24T00:00:00Z",
        "reference": {"chunks": [{"index": 3, "dataset_id": kb_id, "content": "gone"}], "doc_aggs": []},
    })
    with DB.connection_context():
        from api.db.models import Knowledgebase
        Knowledgebase.delete().where(Knowledgebase.id == kb_id).execute()
    assert svc.get_session(world.principal(world.b), chat["id"], session["id"])["messages"][0]["reference"]["chunks"] == [{"index": 3, "unavailable": True}]


def test_stored_internal_message_fields_are_not_returned(world):
    kb_id = dataset(world.tenant, world.a, "team")
    chat = create(world, world.a, permission="team", kb_ids=[kb_id])
    session = svc.create_session(world.principal(world.a), chat["id"])
    message = {
        "id": uuid.uuid4().hex, "role": "assistant", "content": "answer", "created_at": "2026-10-24T00:00:00Z", "finish": "complete",
        "status": "internal", "api_key": "must-not-leak", "feedback_comment": "private note",
        "reference": {"chunks": [{"index": 0, "dataset_id": kb_id, "content": "visible", "api_key": "must-not-leak"}], "doc_aggs": []},
    }
    with DB.connection_context():
        Conversation.update(message=[message]).where(Conversation.id == session["id"]).execute()
    public = svc.get_session(world.principal(world.a), chat["id"], session["id"])["messages"][0]
    assert "status" not in public and "api_key" not in public and "feedback_comment" not in public
    assert "api_key" not in public["reference"]["chunks"][0]
    assert public["reference"]["chunks"][0]["content"] == "visible"


def test_rate_guard_rejects_second_hit_with_retry_after(world):
    settings = dataclasses.replace(load_settings(), chat=dataclasses.replace(ChatSettings(), rate_max=1))
    user = uuid.uuid4().hex
    svc.chat_rate_guard(settings, world.tenant, user)
    with pytest.raises(ServiceError) as err:
        svc.chat_rate_guard(settings, world.tenant, user)
    assert err.value.kind == Kind.RATE_LIMITED and err.value.retry_after >= 1


def test_create_session_waits_for_assistant_row_lock(world):
    chat_id = create(world, world.a, permission="team")["id"]
    held, release, outcome = threading.Event(), threading.Event(), {}

    def holder():
        with DB.connection_context(), DB.atomic():
            Dialog.select(Dialog.id).where(Dialog.id == chat_id).for_update().first()
            held.set()
            release.wait(timeout=20)

    def creator():
        outcome["view"] = svc.create_session(world.principal(world.b), chat_id)

    first = threading.Thread(target=holder)
    first.start()
    assert held.wait(timeout=10)
    second = threading.Thread(target=creator)
    second.start()

    def waiting():
        conn = root_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM information_schema.innodb_trx WHERE trx_state = 'LOCK WAIT' AND trx_query LIKE '%`dialog`%'")
                return cur.fetchone()[0] > 0
        finally:
            conn.close()

    try:
        wait_until(waiting, timeout=15, interval=0.1)
        assert outcome == {}
    finally:
        release.set()
        first.join(timeout=20)
        second.join(timeout=20)
    assert outcome["view"]["chat_id"] == chat_id


@pytest.mark.parametrize("sid", ["bad", "", "x" * 32])
def test_malformed_or_absent_session_id_is_not_found(world, sid):
    chat = create(world, world.a)
    with pytest.raises(ServiceError) as err:
        svc.get_session(world.principal(world.a), chat["id"], sid)
    assert err.value.kind == Kind.NOT_FOUND
