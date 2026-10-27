"""Private chat sessions through Nginx and the running stack (plan 05-09)."""
# ruff: noqa: F401, F811 -- imported fixtures are discovered by pytest and shadowed by test parameters.
from __future__ import annotations

import json
import uuid

import httpx
import pytest

from test.helpers.accounts import unique_name
from test.testcases.test_chat_assistant_flow import CHATS, Team, clean, fake, identical_404, made, registry, team
from test.testcases.test_dataset_flow import DATASETS
from test.testcases.test_provider_flow import api, ok, sql

pytestmark = pytest.mark.e2e


def sessions(chat_id: str) -> str:
    return f"{CHATS}/{chat_id}/sessions"


def session_path(chat_id: str, session_id: str) -> str:
    return f"{sessions(chat_id)}/{session_id}"


def test_create_read_and_list_own_session(ingress: httpx.Client, team: Team):
    chat = made(ingress, team, team.a, permission="team")
    path = sessions(chat["id"])
    created = ok(clean(api(ingress, "POST", path, team.a.token, body={})))
    assert created["chat_id"] == chat["id"] and created["messages"] == [] and created["has_earlier"] is False
    assert ok(clean(api(ingress, "GET", session_path(chat["id"], created["id"]), team.a.token))) == created
    assert [item["id"] for item in ok(clean(api(ingress, "GET", path, team.a.token)))["items"]] == [created["id"]]


def new_session(ingress: httpx.Client, team: Team, who=None, chat_id: str | None = None):
    chat_id = chat_id or made(ingress, team, team.a, permission="team")["id"]
    who = who or team.a
    return chat_id, ok(clean(api(ingress, "POST", sessions(chat_id), who.token, body={})))


def seed(session_id: str, messages: list[dict]):
    sql("UPDATE `conversation` SET `message` = %s WHERE `id` = %s", (json.dumps(messages), session_id))


def assistant_message(*, finish: str = "complete", reference=None):
    return {
        "id": uuid.uuid4().hex,
        "role": "assistant",
        "content": "answer",
        "created_at": "2026-10-24T00:00:00Z",
        "finish": finish,
        "reference": reference or {"chunks": [], "doc_aggs": []},
        "feedback": None,
    }


def test_teammate_sees_only_their_own_sessions(ingress: httpx.Client, team: Team):
    chat_id, a_session = new_session(ingress, team)
    _, b_session = new_session(ingress, team, team.b, chat_id)
    a_list = ok(clean(api(ingress, "GET", sessions(chat_id), team.a.token)))["items"]
    b_list = ok(clean(api(ingress, "GET", sessions(chat_id), team.b.token)))["items"]
    assert [s["id"] for s in a_list] == [a_session["id"]]
    assert [s["id"] for s in b_list] == [b_session["id"]]


def test_teammate_session_id_is_identical_to_random_404(ingress: httpx.Client, team: Team):
    chat_id, session = new_session(ingress, team)
    path = session_path(chat_id, session["id"])
    absent = session_path(chat_id, uuid.uuid4().hex)
    identical_404(clean(api(ingress, "GET", path, team.b.token)), clean(api(ingress, "GET", absent, team.b.token)))
    identical_404(clean(api(ingress, "DELETE", path, team.b.token)), clean(api(ingress, "DELETE", absent, team.b.token)))


def test_deleting_own_session_removes_it(ingress: httpx.Client, team: Team):
    chat_id, session = new_session(ingress, team)
    path = session_path(chat_id, session["id"])
    assert ok(clean(api(ingress, "DELETE", path, team.a.token))) == {"deleted": session["id"]}
    identical_404(clean(api(ingress, "GET", path, team.a.token)))


def test_feedback_on_completed_answer_is_visible_on_read(ingress: httpx.Client, team: Team):
    chat_id, session = new_session(ingress, team)
    message = assistant_message()
    seed(session["id"], [message])
    path = session_path(chat_id, session["id"])
    feedback = path + f"/messages/{message['id']}/feedback"
    assert ok(clean(api(ingress, "POST", feedback, team.a.token, body={"thumb": "up"}))) == {"message_id": message["id"], "feedback": "up"}
    assert ok(clean(api(ingress, "GET", path, team.a.token)))["messages"][0]["feedback"] == "up"


@pytest.mark.parametrize("role,finish", [("user", "complete"), ("assistant", "stopped"), ("assistant", "failed")])
def test_feedback_refuses_non_completed_assistant_messages(ingress: httpx.Client, team: Team, role: str, finish: str):
    chat_id, session = new_session(ingress, team)
    message = assistant_message(finish=finish)
    message["role"] = role
    seed(session["id"], [message])
    path = session_path(chat_id, session["id"]) + f"/messages/{message['id']}/feedback"
    identical_404(clean(api(ingress, "POST", path, team.a.token, body={"thumb": "up"})))


def test_feedback_refuses_unknown_message_and_teammate(ingress: httpx.Client, team: Team):
    chat_id, session = new_session(ingress, team)
    message = assistant_message()
    seed(session["id"], [message])
    base = session_path(chat_id, session["id"]) + "/messages/"
    identical_404(clean(api(ingress, "POST", base + uuid.uuid4().hex + "/feedback", team.a.token, body={"thumb": "up"})))
    identical_404(clean(api(ingress, "POST", base + message["id"] + "/feedback", team.b.token, body={"thumb": "up"})))


def test_before_cursor_pages_120_messages(ingress: httpx.Client, team: Team):
    chat_id, session = new_session(ingress, team)
    messages = [{"id": uuid.uuid4().hex, "role": "user", "content": str(i), "created_at": "2026-10-24T00:00:00Z"} for i in range(120)]
    seed(session["id"], messages)
    path = session_path(chat_id, session["id"])
    first = ok(clean(api(ingress, "GET", path, team.a.token)))
    second = ok(clean(api(ingress, "GET", path, team.a.token, params={"before": first["messages"][0]["id"]})))
    third = ok(clean(api(ingress, "GET", path, team.a.token, params={"before": second["messages"][0]["id"]})))
    assert [len(p["messages"]) for p in (first, second, third)] == [50, 50, 20]
    assert [p["has_earlier"] for p in (first, second, third)] == [True, True, False]
    assert [m["content"] for p in (third, second, first) for m in p["messages"]] == [str(i) for i in range(120)]


def test_reference_redacts_after_dataset_flips_to_me(ingress: httpx.Client, team: Team):
    kb = ok(clean(api(ingress, "POST", DATASETS, team.a.token, body={"name": unique_name("session-kb"), "permission": "team", "tenant_id": team.owner.tenant_id})))['id']
    chat = made(ingress, team, team.a, permission="team", kb_ids=[kb])
    chat_id = chat["id"]
    _, a_session = new_session(ingress, team, team.a, chat_id)
    _, b_session = new_session(ingress, team, team.b, chat_id)
    reference = {"chunks": [{"index": 7, "dataset_id": kb, "content": "hidden text"}], "doc_aggs": []}
    seed(a_session["id"], [assistant_message(reference=reference)])
    seed(b_session["id"], [assistant_message(reference=reference)])
    ok(clean(api(ingress, "PUT", f"{DATASETS}/{kb}", team.a.token, body={"permission": "me"})))
    b_chunk = ok(clean(api(ingress, "GET", session_path(chat_id, b_session["id"]), team.b.token)))["messages"][0]["reference"]["chunks"]
    a_chunk = ok(clean(api(ingress, "GET", session_path(chat_id, a_session["id"]), team.a.token)))["messages"][0]["reference"]["chunks"]
    assert b_chunk == [{"index": 7, "unavailable": True}]
    assert a_chunk[0]["content"] == "hidden text"


def test_stored_internal_fields_do_not_surface_over_http(ingress: httpx.Client, team: Team):
    chat = made(ingress, team, team.a, permission="team", kb_ids=[team.team_dataset])
    chat_id, session = new_session(ingress, team, team.a, chat["id"])
    message = assistant_message(reference={
        "chunks": [{"index": 0, "dataset_id": team.team_dataset, "content": "visible", "api_key": "private-key"}],
        "doc_aggs": [],
    })
    message.update(status="internal", api_key="private-key", feedback_comment="private note")
    seed(session["id"], [message])
    response = clean(api(ingress, "GET", session_path(chat_id, session["id"]), team.a.token))
    public = ok(response)["messages"][0]
    assert "status" not in public and "api_key" not in public and "feedback_comment" not in public
    assert "api_key" not in public["reference"]["chunks"][0]


@pytest.mark.parametrize("bad", ["bad", "x" * 32])
def test_malformed_or_absent_session_is_404(ingress: httpx.Client, team: Team, bad: str):
    chat_id, _ = new_session(ingress, team)
    identical_404(clean(api(ingress, "GET", session_path(chat_id, bad), team.a.token)))


@pytest.mark.parametrize("body", [{"thumb": "maybe"}, {"thumb": "up", "status": "x"}])
def test_feedback_body_validation(ingress: httpx.Client, team: Team, body: dict):
    chat_id, session = new_session(ingress, team)
    message = assistant_message()
    seed(session["id"], [message])
    resp = clean(api(ingress, "POST", session_path(chat_id, session["id"]) + f"/messages/{message['id']}/feedback", team.a.token, body=body))
    assert resp.status_code == 400


@pytest.mark.parametrize("params", [{"page": "0"}, {"page_size": "101"}])
def test_list_rejects_bad_paging(ingress: httpx.Client, team: Team, params: dict[str, str]):
    chat_id, _ = new_session(ingress, team)
    resp = clean(api(ingress, "GET", sessions(chat_id), team.a.token, params=params))
    assert resp.status_code == 400 and resp.json()["data"]["reason"] == "fields_invalid"
