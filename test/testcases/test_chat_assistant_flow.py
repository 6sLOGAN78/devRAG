"""Chat assistants end to end through Nginx on the running stack (plan 05-08; CHAT-01..07, D-08..D-11, D-19, D-23..D-26).

Nothing of devRag is replaced: Nginx, the app and MySQL are the running stack. The loopback provider is only the third party's end of the wire that a
provider save needs, so the workspace has a chat model to bind. Sessions of other members are inserted straight into the ``conversation`` table, as the
session routes of plan 05-09 will write them, because the rulings under test (narrowing, cascade) are about those rows.

Workspace: an owner, an admin, two members (A and B) and an outsider with a workspace of their own. Every test creates the assistants it needs under
unique names, so the tests do not depend on one another.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest

from test.helpers.accounts import Account, AccountRegistry, unique_name
from test.helpers.fake_provider import FakeProvider, running_stack_fake_provider
from test.testcases.conftest import BASE_URL
from test.testcases.test_dataset_flow import DATASETS, workspace
from test.testcases.test_provider_flow import COMPAT, KEY_ONE, NOT_FOUND, TOKENS, api, join, ok, sql

pytestmark = pytest.mark.e2e

CHATS = "/api/v1/chats"
MODEL = f"fake-chat@{COMPAT}"
FORBIDDEN = {"code": 403, "message": "forbidden", "data": None}
BANNED_KEYS = {"dialog_id", "status", "source", "password", "secret", "salt", "ticket", "otp", "access_token", "api_key", "tenant_llm_id", "tenant_rerank_id"}
LIST_KEYS = {
    "id", "name", "permission", "created_by", "kb_ids", "unavailable_datasets", "llm_id", "rerank_id", "similarity_threshold", "vector_similarity_weight",
    "top_n", "prompt_config", "llm_setting", "update_time",
}  # fmt: skip
DETAIL_KEYS = LIST_KEYS | {"icon"}
PROMPT_KEYS = {"system", "prologue", "empty_response"}


@dataclass
class Team:
    owner: Account
    admin: Account
    a: Account  # a normal member
    b: Account  # another normal member
    outsider: Account  # owner of a workspace of their own
    team_dataset: str  # created by member A, permission team
    me_dataset: str  # created by member A, permission me


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
def team(ingress: httpx.Client, registry: AccountRegistry, fake: FakeProvider) -> Team:
    owner = workspace(ingress, registry, fake, "chatown")
    admin, a, b = (registry.register(prefix=p) for p in ("chatadm", "chata", "chatb"))
    join(ingress, owner, admin, "admin")
    join(ingress, owner, a)
    join(ingress, owner, b)
    outsider = workspace(ingress, registry, fake, "chatout")
    scope = {"tenant_id": owner.tenant_id}
    team_dataset = ok(api(ingress, "POST", DATASETS, a.token, body={"name": unique_name("chat-team"), "permission": "team", **scope}))["id"]
    me_dataset = ok(api(ingress, "POST", DATASETS, a.token, body={"name": unique_name("chat-me"), **scope}))["id"]
    return Team(owner, admin, a, b, outsider, team_dataset, me_dataset)


def keys_in(node: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(str(key))
            found |= keys_in(value)
    elif isinstance(node, list):
        for item in node:
            found |= keys_in(item)
    return found


def clean(resp: httpx.Response) -> httpx.Response:
    """The answer holds no internal column and no provider key."""
    assert keys_in(resp.json()).isdisjoint(BANNED_KEYS), (keys_in(resp.json()) & BANNED_KEYS, resp.text)
    assert KEY_ONE not in resp.text
    return resp


def name_of(prefix: str = "flow") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def make(ingress: httpx.Client, t: Team, who: Account, **body: Any) -> httpx.Response:
    """Create in the owner's workspace as ``who`` (the owner needs no workspace named; a member does)."""
    payload = {"name": name_of(), "llm_id": MODEL, "tenant_id": t.owner.tenant_id, **body}
    return clean(api(ingress, "POST", CHATS, who.token, body=payload))


def made(ingress: httpx.Client, t: Team, who: Account, **body: Any) -> dict[str, Any]:
    return ok(make(ingress, t, who, **body))


def chat_path(chat_id: str) -> str:
    return f"{CHATS}/{chat_id}"


def read(ingress: httpx.Client, who: Account, chat_id: str) -> httpx.Response:
    return clean(api(ingress, "GET", chat_path(chat_id), who.token))


def change(ingress: httpx.Client, who: Account, chat_id: str, **body: Any) -> httpx.Response:
    return clean(api(ingress, "PUT", chat_path(chat_id), who.token, body=body))


def remove(ingress: httpx.Client, who: Account, chat_id: str) -> httpx.Response:
    return clean(api(ingress, "DELETE", chat_path(chat_id), who.token))


def listing(ingress: httpx.Client, t: Team, who: Account, **params: str) -> dict[str, Any]:
    query = {"tenant_id": t.owner.tenant_id, "page_size": "100", **params}
    return ok(clean(api(ingress, "GET", CHATS, who.token, params=query)))


def reason(resp: httpx.Response) -> str:
    return str(resp.json()["data"]["reason"])


def add_session(chat_id: str, who: Account) -> str:
    """A member's session with the assistant, written the way plan 05-09 will write it."""
    session_id = uuid.uuid4().hex
    sql("INSERT INTO `conversation` (`id`, `dialog_id`, `user_id`, `name`, `message`, `reference`) VALUES (%s, %s, %s, %s, %s, %s)", (session_id, chat_id, who.user_id, "chat", "[]", "[]"))
    return session_id


def session_count(chat_id: str) -> int:
    return int(sql("SELECT COUNT(*) FROM `conversation` WHERE `dialog_id` = %s", (chat_id,))[0][0])


def row_exists(chat_id: str) -> bool:
    return int(sql("SELECT COUNT(*) FROM `dialog` WHERE `id` = %s", (chat_id,))[0][0]) == 1


def identical_404(*responses: httpx.Response) -> None:
    """Every response is the bare not-found answer, byte for byte."""
    for resp in responses:
        assert resp.status_code == 404 and resp.json() == NOT_FOUND, resp.text
    assert len({r.text for r in responses}) == 1


# ----------------------------------------------------------------------------- create and read (CHAT-01, CHAT-02)


def test_a_member_creates_a_private_assistant_with_the_documented_defaults(ingress: httpx.Client, team: Team) -> None:
    data = made(ingress, team, team.a)
    assert set(data) == DETAIL_KEYS | {"members_with_chats"}, "the creator can manage it, so the count is present"
    assert data["permission"] == "me" and data["created_by"] == team.a.user_id and data["llm_id"] == MODEL
    assert data["kb_ids"] == [] and data["unavailable_datasets"] == 0 and data["members_with_chats"] == 0
    assert data["rerank_id"] == "" and data["icon"] in (None, "")
    assert set(data["prompt_config"]) == PROMPT_KEYS and data["prompt_config"]["empty_response"]
    assert 0 <= data["similarity_threshold"] <= 1 and 0 <= data["vector_similarity_weight"] <= 1 and data["top_n"] >= 1


def test_reading_an_assistant_answers_what_creating_it_answered(ingress: httpx.Client, team: Team) -> None:
    created = made(ingress, team, team.a, kb_ids=[team.team_dataset], top_n=7)
    assert ok(read(ingress, team.a, created["id"])) == created
    assert created["kb_ids"] == [team.team_dataset] and created["top_n"] == 7


def test_a_team_assistant_is_created_with_a_team_dataset_and_a_teammate_reads_it(ingress: httpx.Client, team: Team) -> None:
    created = made(ingress, team, team.a, permission="team", kb_ids=[team.team_dataset])
    seen = ok(read(ingress, team.b, created["id"]))
    assert seen["kb_ids"] == [team.team_dataset] and seen["permission"] == "team"
    assert "members_with_chats" not in seen, "a reader who cannot manage the assistant is not told who else chats with it"
    assert set(seen) == DETAIL_KEYS


def test_the_creator_id_and_workspace_are_never_taken_from_the_body(ingress: httpx.Client, team: Team) -> None:
    for field in ("created_by", "tenant_llm_id", "id", "dialog_id", "status", "source"):
        resp = make(ingress, team, team.a, **{field: team.owner.user_id})
        assert resp.status_code == 400, f"{field}: HTTP {resp.status_code}"


def test_a_prompt_and_settings_sent_on_create_are_stored_and_returned(ingress: httpx.Client, team: Team) -> None:
    created = made(
        ingress, team, team.a,
        prompt_config={"system": "Answer only from the passages.", "prologue": "Hello!", "empty_response": "Nothing found."},
        llm_setting={"temperature": 0, "max_tokens": 256}, similarity_threshold=0.35, vector_similarity_weight=0.6, top_n=4,
    )  # fmt: skip
    assert created["prompt_config"] == {"system": "Answer only from the passages.", "prologue": "Hello!", "empty_response": "Nothing found."}
    assert created["llm_setting"]["temperature"] == 0 and created["llm_setting"]["max_tokens"] == 256
    assert (created["similarity_threshold"], created["vector_similarity_weight"], created["top_n"]) == (0.35, 0.6, 4)


def test_an_unknown_field_an_over_long_name_and_a_missing_model_are_refused_with_a_typed_reason(ingress: httpx.Client, team: Team) -> None:
    assert make(ingress, team, team.a, nonsense=1).status_code == 400
    long_name = make(ingress, team, team.a, name="n" * 200)
    assert long_name.status_code == 400 and reason(long_name) == "fields_invalid"
    blank = make(ingress, team, team.a, name="   ")
    assert blank.status_code == 400 and reason(blank) == "fields_invalid"
    odd = make(ingress, team, team.a, top_n=500)
    assert odd.status_code == 400 and reason(odd) == "fields_invalid"
    body = {"name": name_of(), "tenant_id": team.owner.tenant_id}
    missing = clean(api(ingress, "POST", CHATS, team.a.token, body=body))
    assert missing.status_code == 400 and reason(missing) == "model_unavailable"


def test_a_chat_model_the_workspace_does_not_have_is_refused_as_unavailable(ingress: httpx.Client, team: Team) -> None:
    for body in ({"llm_id": f"nothing@{COMPAT}"}, {"llm_id": "garbage"}, {"llm_id": MODEL, "rerank_id": f"nothing@{COMPAT}"}):
        resp = make(ingress, team, team.a, **body)
        assert resp.status_code == 400 and reason(resp) == "model_unavailable", body


def test_a_duplicate_name_is_a_conflict_whatever_the_case(ingress: httpx.Client, team: Team) -> None:
    name = name_of("Dup")
    made(ingress, team, team.a, name=name)
    for other in (name, name.lower(), name.upper()):
        resp = make(ingress, team, team.b, name=other)
        assert resp.status_code == 409 and reason(resp) == "duplicate_name", other


# ----------------------------------------------------------------------------- binding (CHAT-01, D-10)


def test_a_team_assistant_cannot_bind_a_private_dataset_and_the_conflict_names_it(ingress: httpx.Client, team: Team) -> None:
    resp = make(ingress, team, team.a, permission="team", kb_ids=[team.me_dataset])
    assert resp.status_code == 409 and reason(resp) == "assistant_dataset_not_shared"
    assert resp.json()["data"]["dataset_ids"] == [team.me_dataset]
    private = made(ingress, team, team.a, kb_ids=[team.me_dataset])
    assert private["kb_ids"] == [team.me_dataset], "a private assistant binds a private dataset of its creator"
    widen = change(ingress, team.a, private["id"], permission="team")
    assert widen.status_code == 409 and reason(widen) == "assistant_dataset_not_shared" and widen.json()["data"]["dataset_ids"] == [team.me_dataset]
    assert ok(read(ingress, team.a, private["id"]))["permission"] == "me", "the refused save changed nothing"


def test_a_dataset_of_another_workspace_or_one_that_does_not_exist_is_a_not_found_with_the_dataset_reason(ingress: httpx.Client, team: Team) -> None:
    foreign = ok(api(ingress, "POST", DATASETS, team.outsider.token, body={"name": name_of("foreign")}))["id"]
    for dataset_id in (foreign, uuid.uuid4().hex, "not-an-id"):
        resp = make(ingress, team, team.a, kb_ids=[dataset_id])
        assert resp.status_code == 404 and resp.json()["data"] == {"reason": "dataset_not_found"}, dataset_id
        assert resp.json()["message"] == "not found"
    own = made(ingress, team, team.a)
    resp = change(ingress, team.a, own["id"], kb_ids=[foreign])
    assert resp.status_code == 404 and resp.json()["data"] == {"reason": "dataset_not_found"}
    assert ok(read(ingress, team.a, own["id"]))["kb_ids"] == []


def test_a_member_cannot_bind_a_dataset_they_cannot_open(ingress: httpx.Client, team: Team) -> None:
    resp = make(ingress, team, team.b, kb_ids=[team.me_dataset])
    assert resp.status_code == 404 and resp.json()["data"] == {"reason": "dataset_not_found"}, "member A's private dataset is invisible to member B"


# ----------------------------------------------------------------------------- update (CHAT-03)


def test_updating_only_the_name_leaves_every_other_field_unchanged(ingress: httpx.Client, team: Team) -> None:
    created = made(
        ingress, team, team.a, kb_ids=[team.team_dataset], top_n=9, similarity_threshold=0.4,
        prompt_config={"system": "Stay on topic.", "prologue": "Hi there", "empty_response": "No luck."}, llm_setting={"temperature": 0.5},
    )  # fmt: skip
    renamed = ok(change(ingress, team.a, created["id"], name=name_of("renamed")))
    assert renamed["name"] != created["name"]
    for key in DETAIL_KEYS - {"name", "update_time"}:
        assert renamed[key] == created[key], key
    assert renamed["update_time"] >= created["update_time"]


def test_a_partial_prompt_and_setting_update_merges_over_the_stored_values(ingress: httpx.Client, team: Team) -> None:
    created = made(ingress, team, team.a, prompt_config={"system": "Keep this.", "prologue": "Old greeting", "empty_response": "Keep that."}, llm_setting={"temperature": 0.3, "top_p": 0.5})
    updated = ok(change(ingress, team.a, created["id"], prompt_config={"prologue": "New greeting"}, llm_setting={"temperature": 0.9}, rerank_id=None, icon=None))
    assert updated["prompt_config"] == {"system": "Keep this.", "prologue": "New greeting", "empty_response": "Keep that."}
    assert updated["llm_setting"]["temperature"] == 0.9 and updated["llm_setting"]["top_p"] == 0.5


def test_an_update_refuses_an_empty_body_a_null_for_a_required_field_and_values_out_of_range(ingress: httpx.Client, team: Team) -> None:
    created = made(ingress, team, team.a)
    for body in ({}, {"name": None}, {"permission": "everyone"}, {"top_n": 0}, {"vector_similarity_weight": 2}, {"llm_setting": {"temperature": 9}}, {"status": "0"}):
        resp = change(ingress, team.a, created["id"], **body)
        assert resp.status_code == 400, (body, resp.text)
    assert ok(read(ingress, team.a, created["id"])) == created, "no refused save changed the assistant"
    clash = made(ingress, team, team.a)
    resp = change(ingress, team.a, clash["id"], name=created["name"])
    assert resp.status_code == 409 and reason(resp) == "duplicate_name"


# ----------------------------------------------------------------------------- list (CHAT-02)


def test_the_list_pages_newest_first_and_counts_the_total(ingress: httpx.Client, team: Team) -> None:
    prefix = name_of("page")
    ids = [made(ingress, team, team.a, name=f"{prefix}-{n}")["id"] for n in range(3)]
    first = listing(ingress, team, team.a, keywords=prefix, page="1", page_size="2")
    second = listing(ingress, team, team.a, keywords=prefix, page="2", page_size="2")
    assert first["total"] == second["total"] == 3 and len(first["items"]) == 2 and len(second["items"]) == 1
    assert {i["id"] for i in first["items"] + second["items"]} == set(ids)
    assert all(set(i) == LIST_KEYS for i in first["items"]), "a list item carries no icon and no member count"
    assert first["items"][0]["update_time"] >= first["items"][1]["update_time"]


def test_keywords_match_a_part_of_the_name_and_percent_and_underscore_are_plain_characters(ingress: httpx.Client, team: Team) -> None:
    tag = uuid.uuid4().hex[:8]
    literal = made(ingress, team, team.a, name=f"{tag}-50%_off")["id"]
    other = made(ingress, team, team.a, name=f"{tag}-50xyoff")["id"]
    assert {i["id"] for i in listing(ingress, team, team.a, keywords=f"{tag}-50")["items"]} == {literal, other}
    assert {i["id"] for i in listing(ingress, team, team.a, keywords=f"{tag}-50%_")["items"]} == {literal}
    assert {i["id"] for i in listing(ingress, team, team.a, keywords=tag.upper())["items"]} == {literal, other}, "case does not matter"
    assert listing(ingress, team, team.a, keywords="%")["total"] >= 1 and all("%" in i["name"] for i in listing(ingress, team, team.a, keywords="%")["items"])


def test_a_teammate_lists_their_own_assistants_and_every_team_one_and_never_a_private_one_of_someone_else(ingress: httpx.Client, team: Team) -> None:
    tag = name_of("vis")
    private_a = made(ingress, team, team.a, name=f"{tag}-a-me")["id"]
    shared_a = made(ingress, team, team.a, name=f"{tag}-a-team", permission="team")["id"]
    private_b = made(ingress, team, team.b, name=f"{tag}-b-me")["id"]
    ids = {who.nickname: {i["id"] for i in listing(ingress, team, who, keywords=tag)["items"]} for who in (team.a, team.b, team.owner, team.admin)}
    assert ids[team.a.nickname] == {private_a, shared_a}
    assert ids[team.b.nickname] == {shared_a, private_b}
    assert ids[team.owner.nickname] == ids[team.admin.nickname] == {shared_a}, "owner and admin see no one's private assistant"


def test_paging_and_keyword_limits_are_enforced_with_a_typed_reason(ingress: httpx.Client, team: Team) -> None:
    for params in ({"page_size": "101"}, {"page_size": "0"}, {"page": "0"}, {"page": "abc"}, {"keywords": "k" * 129}):
        resp = clean(api(ingress, "GET", CHATS, team.a.token, params={"tenant_id": team.owner.tenant_id, **params}))
        assert resp.status_code == 400 and reason(resp) == "fields_invalid", params
    default = ok(api(ingress, "GET", CHATS, team.a.token, params={"tenant_id": team.owner.tenant_id}))
    assert set(default) == {"items", "total"} and len(default["items"]) <= 20, "the default page holds at most 20"


# ----------------------------------------------------------------------------- visibility (D-09, D-19)


def test_a_private_assistant_is_an_identical_404_for_the_owner_the_admin_and_a_teammate(ingress: httpx.Client, team: Team) -> None:
    private = made(ingress, team, team.a)["id"]
    absent = uuid.uuid4().hex
    reference = api(ingress, "GET", chat_path(absent), team.owner.token)
    identical_404(reference)
    for who in (team.owner, team.admin, team.b):
        identical_404(
            reference,
            read(ingress, who, private),
            change(ingress, who, private, name=name_of("takeover")),
            change(ingress, who, absent, name=name_of("takeover")),
            remove(ingress, who, private),
            remove(ingress, who, absent),
        )
    assert row_exists(private) and ok(read(ingress, team.a, private))["permission"] == "me", "nothing was changed or deleted"


def test_a_malformed_id_and_another_workspaces_assistant_get_the_same_404_as_a_random_id(ingress: httpx.Client, team: Team) -> None:
    foreign = ok(api(ingress, "POST", CHATS, team.outsider.token, body={"name": name_of("theirs"), "llm_id": MODEL, "permission": "team"}))["id"]
    reference = api(ingress, "GET", chat_path(uuid.uuid4().hex), team.owner.token)
    identical_404(
        reference,
        read(ingress, team.owner, "not-an-id"),
        read(ingress, team.owner, "x" * 40),
        read(ingress, team.owner, foreign),
        read(ingress, team.a, foreign),
        change(ingress, team.owner, foreign, name=name_of("takeover")),
        remove(ingress, team.owner, foreign),
    )
    assert row_exists(foreign)
    mine = clean(api(ingress, "GET", chat_path(foreign), team.outsider.token))
    assert mine.status_code == 200, "its own workspace still reads it"


def test_a_workspace_that_is_not_the_callers_is_the_one_404_on_create_and_list(ingress: httpx.Client, team: Team) -> None:
    for who in (team.outsider, team.owner):
        other = team.owner if who is team.outsider else team.outsider
        body = {"name": name_of(), "llm_id": MODEL, "tenant_id": other.tenant_id}
        identical_404(clean(api(ingress, "POST", CHATS, who.token, body=body)), clean(api(ingress, "GET", CHATS, who.token, params={"tenant_id": other.tenant_id})))
    assert api(ingress, "GET", CHATS, team.a.token, params={"tenant_id": "nope"}).status_code == 404


def test_a_teammate_reads_a_team_assistant_but_cannot_change_or_delete_it(ingress: httpx.Client, team: Team) -> None:
    shared = made(ingress, team, team.a, permission="team", kb_ids=[team.team_dataset])
    for resp in (change(ingress, team.b, shared["id"], name=name_of("takeover")), remove(ingress, team.b, shared["id"])):
        assert resp.status_code == 403 and resp.json() == FORBIDDEN
    assert ok(read(ingress, team.a, shared["id"])) | {"update_time": 0} == shared | {"update_time": 0}, "unchanged"
    assert row_exists(shared["id"])


def test_the_owner_and_the_admin_may_edit_and_delete_a_team_assistant_they_did_not_create(ingress: httpx.Client, team: Team) -> None:
    shared = made(ingress, team, team.a, permission="team")["id"]
    assert ok(change(ingress, team.owner, shared, top_n=11))["top_n"] == 11
    assert ok(change(ingress, team.admin, shared, name=name_of("by-admin")))["name"].startswith("by-admin")
    assert ok(remove(ingress, team.admin, shared)) == {"deleted": shared}
    other = made(ingress, team, team.a, permission="team")["id"]
    assert ok(remove(ingress, team.owner, other)) == {"deleted": other}
    identical_404(read(ingress, team.owner, shared), read(ingress, team.a, other))
    assert not row_exists(shared) and not row_exists(other)


def test_only_a_manager_is_told_how_many_other_members_chat_with_the_assistant(ingress: httpx.Client, team: Team) -> None:
    shared = made(ingress, team, team.a, permission="team")["id"]
    add_session(shared, team.b)
    add_session(shared, team.b)
    add_session(shared, team.owner)
    add_session(shared, team.a)
    assert ok(read(ingress, team.a, shared))["members_with_chats"] == 2, "distinct members other than the creator"
    assert ok(read(ingress, team.admin, shared))["members_with_chats"] == 3, "the admin counts everyone but the admin"
    assert "members_with_chats" not in ok(read(ingress, team.b, shared))


# ----------------------------------------------------------------------------- narrowing and delete (D-23, D-26)


def test_narrowing_to_private_is_refused_while_another_member_has_a_chat_and_works_after(ingress: httpx.Client, team: Team) -> None:
    shared = made(ingress, team, team.a, permission="team", kb_ids=[team.team_dataset])["id"]
    session = add_session(shared, team.b)
    add_session(shared, team.a)
    refused = change(ingress, team.a, shared, permission="me")
    assert refused.status_code == 409 and reason(refused) == "assistant_has_member_chats" and refused.json()["data"]["count"] == 1
    assert row_exists(shared) and session_count(shared) == 2, "nothing was deleted by the refused save"
    assert ok(read(ingress, team.a, shared))["permission"] == "team"
    sql("DELETE FROM `conversation` WHERE `id` = %s", (session,))
    narrowed = ok(change(ingress, team.a, shared, permission="me"))
    assert narrowed["permission"] == "me"
    identical_404(read(ingress, team.admin, shared), read(ingress, team.b, shared))


def test_an_admin_narrowing_is_refused_the_same_way_and_the_count_excludes_the_creator_only(ingress: httpx.Client, team: Team) -> None:
    shared = made(ingress, team, team.a, permission="team")["id"]
    add_session(shared, team.b)
    refused = change(ingress, team.admin, shared, permission="me")
    assert refused.status_code == 409 and refused.json()["data"]["count"] == 1
    sql("DELETE FROM `conversation` WHERE `dialog_id` = %s", (shared,))
    assert ok(change(ingress, team.admin, shared, permission="me"))["permission"] == "me"
    identical_404(read(ingress, team.admin, shared), read(ingress, team.owner, shared))
    assert row_exists(shared), "the admin narrowed it and can no longer see it; it still exists for its creator"
    assert ok(read(ingress, team.a, shared))["permission"] == "me"


def test_a_dataset_the_saver_cannot_open_is_kept_when_they_save_something_else(ingress: httpx.Client, team: Team) -> None:
    flipping = ok(api(ingress, "POST", DATASETS, team.a.token, body={"name": unique_name("chat-flip"), "permission": "team", "tenant_id": team.owner.tenant_id}))["id"]
    shared = made(ingress, team, team.a, permission="team", kb_ids=[team.team_dataset, flipping])["id"]
    ok(api(ingress, "PUT", f"{DATASETS}/{flipping}", team.a.token, body={"permission": "me"}))
    as_admin = ok(read(ingress, team.admin, shared))
    assert as_admin["kb_ids"] == [team.team_dataset] and as_admin["unavailable_datasets"] == 1, "the admin cannot open the dataset that went private"
    saved = ok(change(ingress, team.admin, shared, name=name_of("admin-save")))
    assert saved["kb_ids"] == [team.team_dataset] and saved["unavailable_datasets"] == 1
    assert set(ok(read(ingress, team.a, shared))["kb_ids"]) == {team.team_dataset, flipping}, "the creator still has both datasets bound"
    again = ok(change(ingress, team.admin, shared, kb_ids=[team.team_dataset]))
    assert again["kb_ids"] == [team.team_dataset]
    assert set(ok(read(ingress, team.a, shared))["kb_ids"]) == {team.team_dataset, flipping}, "choosing the visible ids does not unbind the hidden one"


def test_deleting_an_assistant_removes_every_members_sessions_with_it(ingress: httpx.Client, team: Team) -> None:
    shared = made(ingress, team, team.a, permission="team")["id"]
    for who in (team.a, team.b, team.owner):
        add_session(shared, who)
    survivor = made(ingress, team, team.a, permission="team")["id"]
    add_session(survivor, team.b)
    assert session_count(shared) == 3
    assert ok(remove(ingress, team.a, shared)) == {"deleted": shared}
    assert session_count(shared) == 0 and not row_exists(shared)
    assert session_count(survivor) == 1 and row_exists(survivor), "another assistant's sessions are untouched"
    identical_404(remove(ingress, team.a, shared), read(ingress, team.b, shared))


# ----------------------------------------------------------------------------- credentials and limits


def test_an_api_token_creates_lists_and_deletes_in_its_own_workspace_only(ingress: httpx.Client, team: Team) -> None:
    ingress.cookies.clear()  # token creation is owned by the Go server, so it is not sent through the Python-only helper
    minted = ingress.post(TOKENS, headers={"Authorization": f"Bearer {team.owner.token}"})
    assert minted.status_code == 200, minted.text
    token = minted.json()["data"]["token"]
    created = ok(clean(api(ingress, "POST", CHATS, token, body={"name": name_of("tok"), "llm_id": MODEL})))
    assert created["created_by"] == team.owner.user_id, "a token acts as its user"
    assert created["id"] in {i["id"] for i in ok(clean(api(ingress, "GET", CHATS, token, params={"page_size": "100"})))["items"]}
    foreign = clean(api(ingress, "GET", CHATS, token, params={"tenant_id": team.outsider.tenant_id}))
    identical_404(foreign)
    assert ok(clean(api(ingress, "DELETE", chat_path(created["id"]), token))) == {"deleted": created["id"]}


def test_a_request_without_a_credential_or_with_a_made_up_one_is_refused_before_any_lookup(ingress: httpx.Client, team: Team) -> None:
    target = made(ingress, team, team.a)["id"]
    for method, path in (("GET", CHATS), ("POST", CHATS), ("GET", chat_path(target)), ("PUT", chat_path(target)), ("DELETE", chat_path(target))):
        ingress.cookies.clear()
        for headers in ({}, {"Authorization": "Bearer not-a-real-credential"}):
            resp = ingress.request(method, path, headers=headers, json={} if method in ("POST", "PUT") else None)
            assert resp.status_code == 401, (method, path, resp.status_code)
    assert row_exists(target)


def test_a_body_over_one_mebibyte_is_refused_by_nginx_before_the_app(ingress: httpx.Client, team: Team) -> None:
    ingress.cookies.clear()
    headers = {"Authorization": f"Bearer {team.a.token}", "Content-Type": "application/json"}
    body = b'{"name": "' + b"x" * (2 * 1024 * 1024) + b'"}'
    for method, path in (("POST", CHATS), ("PUT", chat_path(uuid.uuid4().hex))):
        resp = ingress.request(method, path, headers=headers, content=body, timeout=60.0)
        assert resp.status_code == 413 and resp.json() == {"code": 400, "message": "payload too large", "data": None}, (method, resp.text[:100])
        assert "x-api-source" not in resp.headers, "the body reached the app"


def test_no_answer_of_any_row_holds_an_internal_column_or_the_provider_key(ingress: httpx.Client, team: Team) -> None:
    created = make(ingress, team, team.a, permission="team", kb_ids=[team.team_dataset])
    chat_id = ok(created)["id"]
    for resp in (
        created,
        api(ingress, "GET", CHATS, team.a.token, params={"tenant_id": team.owner.tenant_id}),
        read(ingress, team.b, chat_id),
        change(ingress, team.a, chat_id, top_n=5),
        change(ingress, team.b, chat_id, top_n=5),
        remove(ingress, team.a, chat_id),
        read(ingress, team.a, chat_id),
    ):
        clean(resp)
