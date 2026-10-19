"""Chat assistant service against the real MySQL (plan 05-07; CHAT-01..07, D-08..D-11, D-19, D-23..D-26).

Every test registers its own accounts through the running stack and joins them to one workspace through the real team API; the registry removes
exactly those rows (and their assistants and sessions) afterwards. Datasets are inserted as rows of the real ``knowledgebase`` table: the service
only reads their owner, permission, state and embedding model, so no index is needed. Chat, embedding and rerank models are saved through
``tenant_model_service`` like a provider save would.
"""

from __future__ import annotations

import dataclasses
import os
import threading
import uuid
from base64 import urlsafe_b64encode
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

import httpx
import pytest

from api.db.database import DB, init_database
from api.db.models import Conversation, Dialog, Knowledgebase
from api.db.services import dialog_service as svc
from api.db.services import tenant_model_service as models
from api.db.services.auth_service import AUTH_API, AUTH_JWT, Principal
from api.db.services.service_errors import Kind, ServiceError
from api.db.services.tenant_scope import ActingScope, resolve_scope
from common.settings import load_settings
from test.helpers.accounts import Account, AccountRegistry, unique_name
from test.helpers.db import root_connection
from test.helpers.wait import wait_until
from test.testcases.conftest import BASE_URL

pytestmark = pytest.mark.integration

PROVIDER = "OpenRouter"
CHAT_A = f"chat-a@{PROVIDER}"
CHAT_B = f"chat-b@{PROVIDER}"
EMBED_A = f"embed-a@{PROVIDER}"
EMBED_B = f"embed-b@{PROVIDER}"
RERANK_A = f"rerank-a@{PROVIDER}"
PNG = "data:image/png;base64,iVBORw0KGgo="
VIEW_KEYS = {
    "id", "name", "icon", "permission", "created_by", "kb_ids", "unavailable_datasets", "llm_id", "rerank_id", "similarity_threshold",
    "vector_similarity_weight", "top_n", "prompt_config", "llm_setting", "update_time",
}  # fmt: skip
BANNED_KEYS = {"dialog_id", "status", "source", "tenant_id", "tenant_llm_id", "tenant_rerank_id", "kb_id"}


@pytest.fixture(scope="module", autouse=True)
def _bound_database() -> Iterator[None]:
    init_database(load_settings().mysql)
    yield
    DB.close()


@pytest.fixture(scope="module")
def llm():
    settings = load_settings()
    return dataclasses.replace(settings.llm, encryption_key=urlsafe_b64encode(os.urandom(32)).decode(), key_id="k1")


@pytest.fixture
def registry() -> Iterator[AccountRegistry]:
    accounts = AccountRegistry(BASE_URL)
    try:
        yield accounts
    finally:
        accounts.cleanup()


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def join(owner: Account, member: Account, role: str | None = None) -> None:
    """Invite, accept and (for admin) promote through the real team API."""
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as http:
        users = f"/api/v1/tenants/{owner.tenant_id}/users"
        assert http.post(users, headers=_bearer(owner.token), json={"email": member.email}).status_code == 200
        accepted = http.patch(f"/api/v1/tenants/{owner.tenant_id}", headers=_bearer(member.token), json={"action": "accept"})
        assert accepted.status_code == 200, accepted.text
        if role:
            promoted = http.patch(f"{users}/{member.user_id}", headers=_bearer(owner.token), json={"role": role})
            assert promoted.status_code == 200, promoted.text


def configure(llm_settings, account: Account) -> None:
    """Models of this workspace: two chat models, two embedding models and a rerank model."""
    listed = [
        models.NewModel(name="chat-a", model_type="chat", dimension=None, max_tokens=8192),
        models.NewModel(name="chat-b", model_type="chat", dimension=None, max_tokens=8192),
        models.NewModel(name="embed-a", model_type="embedding", dimension=8, max_tokens=8192),
        models.NewModel(name="embed-b", model_type="embedding", dimension=16, max_tokens=8192),
        models.NewModel(name="rerank-a", model_type="rerank", dimension=None, max_tokens=8192),
    ]
    key = "-".join(("sk", "fake", uuid.uuid4().hex[:24]))
    models.save_instance(llm_settings, account.tenant_id, PROVIDER, "default", api_key=key, api_base=None, api_version=None, models=listed, replace_key=True)


@dataclass
class World:
    """One workspace: its owner, an admin and two ordinary members, with the chat models configured."""

    owner: Account
    admin: Account
    a: Account
    b: Account
    outsider: Account

    @property
    def tenant(self) -> str:
        return self.owner.tenant_id

    def principal(self, account: Account, *, auth: str = AUTH_JWT) -> Principal:
        return Principal(account.user_id, account.tenant_id, "owner", auth, False)

    def role(self, account: Account) -> str:
        return {self.owner.user_id: "owner", self.admin.user_id: "admin"}.get(account.user_id, "normal")

    def scope(self, account: Account) -> ActingScope:
        found = resolve_scope(self.principal(account), self.tenant)
        assert found is not None and found.role == self.role(account), found
        return found


@pytest.fixture
def world(llm, registry) -> World:
    owner = registry.register(prefix="dlgo")
    admin, a, b, outsider = (registry.register(prefix=p) for p in ("dlga", "dlm1", "dlm2", "dlout"))
    join(owner, admin, "admin")
    join(owner, a)
    join(owner, b)
    configure(llm, owner)
    configure(llm, outsider)
    return World(owner, admin, a, b, outsider)


def dataset(tenant: str, creator: Account, permission: str = "team", embd_id: str = EMBED_A, name: str | None = None) -> str:
    dataset_id = uuid.uuid4().hex
    with DB.connection_context():
        Knowledgebase.create(
            id=dataset_id, tenant_id=tenant, name=name or unique_name("ds"), embd_id=embd_id, created_by=creator.user_id, permission=permission, status="1"
        )
    return dataset_id


def set_permission(dataset_id: str, permission: str) -> None:
    with DB.connection_context():
        Knowledgebase.update(permission=permission).where(Knowledgebase.id == dataset_id).execute()


def remove_dataset(dataset_id: str) -> None:
    with DB.connection_context():
        Knowledgebase.delete().where(Knowledgebase.id == dataset_id).execute()


def session_of(chat_id: str, account: Account) -> str:
    session_id = uuid.uuid4().hex
    with DB.connection_context():
        Conversation.create(id=session_id, dialog_id=chat_id, user_id=account.user_id, name="chat", message=[], reference=[])
    return session_id


def sessions(chat_id: str) -> int:
    with DB.connection_context():
        return Conversation.select().where(Conversation.dialog_id == chat_id).count()


def stored(chat_id: str) -> dict[str, Any] | None:
    with DB.connection_context():
        row = Dialog.get_or_none(Dialog.id == chat_id)
        return None if row is None else {"kb_ids": row.kb_ids, "permission": row.permission, "name": row.name, "created_by": row.created_by, "status": row.status}


def body(**kw: Any) -> dict[str, Any]:
    return {"name": unique_name("bot"), "llm_id": CHAT_A, **kw}


def create(world: World, who: Account, **kw: Any) -> dict[str, Any]:
    return svc.create_assistant(world.principal(who), world.scope(who), body(**kw))


def get(world: World, who: Account, chat_id: str) -> dict[str, Any]:
    return svc.get_assistant(world.principal(who), chat_id)


def refused(call: Callable[[], Any]) -> ServiceError:
    with pytest.raises(ServiceError) as err:
        call()
    return err.value


# ----------------------------------------------------------------------------- create


def test_member_creates_a_private_assistant_by_default_with_the_documented_view(world):
    view = create(world, world.a, name="First bot")
    assert set(view) == VIEW_KEYS | {"members_with_chats"}, "the creator can manage it, so the detail carries the member count"
    assert not BANNED_KEYS & set(view)
    assert view["permission"] == "me" and view["created_by"] == world.a.user_id
    assert view["name"] == "First bot" and view["icon"] == "" and view["kb_ids"] == [] and view["unavailable_datasets"] == 0
    assert view["llm_id"] == CHAT_A and view["rerank_id"] == "" and view["members_with_chats"] == 0
    assert (view["similarity_threshold"], view["vector_similarity_weight"], view["top_n"]) == (0.2, 0.3, 6)
    assert set(view["prompt_config"]) == {"system", "prologue", "empty_response"} and view["prompt_config"]["empty_response"]
    assert view["llm_setting"] == {"temperature": 0.1, "top_p": 0.3, "frequency_penalty": 0.7, "presence_penalty": 0.4, "max_tokens": 512}
    row = stored(view["id"])
    assert row == {"kb_ids": [], "permission": "me", "name": "First bot", "created_by": world.a.user_id, "status": "1"}
    with DB.connection_context():
        assert Dialog.get_by_id(view["id"]).tenant_id == world.tenant


def test_the_opening_message_and_prompts_are_stored_over_the_defaults(world):
    view = create(world, world.a, prompt_config={"prologue": "Hello!", "empty_response": "Nothing found."}, llm_setting={"temperature": 1.5, "max_tokens": 1024})
    assert view["prompt_config"] == {"system": "", "prologue": "Hello!", "empty_response": "Nothing found."}
    assert view["llm_setting"] == {"temperature": 1.5, "top_p": 0.3, "frequency_penalty": 0.7, "presence_penalty": 0.4, "max_tokens": 1024}


def test_a_team_assistant_is_created_by_any_member_and_visible_to_all(world):
    team = dataset(world.tenant, world.a)
    view = create(world, world.a, permission="team", kb_ids=[team])
    assert view["permission"] == "team" and view["kb_ids"] == [team]
    for who in (world.owner, world.admin, world.b):
        seen = get(world, who, view["id"])
        assert seen["id"] == view["id"] and seen["kb_ids"] == [team], who.nickname


def test_a_duplicate_name_differing_only_by_case_is_a_conflict(world):
    create(world, world.a, name="Support Bot")
    for who, name in ((world.a, "support bot"), (world.b, "SUPPORT BOT")):
        err = refused(lambda who=who, name=name: create(world, who, name=name))
        assert (err.kind, err.reason) == (Kind.CONFLICT, "duplicate_name")


def test_names_are_unique_per_workspace_not_globally(world):
    create(world, world.a, name="Shared Name")
    other = svc.create_assistant(world.principal(world.outsider), resolve_scope(world.principal(world.outsider), None), body(name="Shared Name"))
    assert other["name"] == "Shared Name" and other["id"]


def test_concurrent_creates_with_one_name_produce_one_assistant(world):
    name = unique_name("race")

    def attempt(_: int) -> str:
        try:
            create(world, world.a, name=name)
            return "created"
        except ServiceError as exc:
            return exc.reason

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = sorted(pool.map(attempt, range(4)))
    assert outcomes.count("created") == 1 and set(outcomes) <= {"created", "duplicate_name"}, outcomes


def test_a_team_assistant_cannot_bind_a_private_dataset(world):
    private, team = dataset(world.tenant, world.a, "me"), dataset(world.tenant, world.a, "team")
    err = refused(lambda: create(world, world.a, permission="team", kb_ids=[team, private]))
    assert (err.kind, err.reason) == (Kind.CONFLICT, "assistant_dataset_not_shared")
    assert err.data == {"dataset_ids": [private]}


def test_a_private_assistant_may_bind_any_dataset_its_creator_can_open(world):
    private, theirs = dataset(world.tenant, world.a, "me"), dataset(world.tenant, world.b, "team")
    view = create(world, world.a, kb_ids=[private, theirs])
    assert view["permission"] == "me" and view["kb_ids"] == [private, theirs]


def test_a_dataset_the_creator_cannot_open_is_dataset_not_found_even_for_a_private_assistant(world):
    theirs = dataset(world.tenant, world.b, "me")
    for who in (world.a, world.admin, world.owner):
        err = refused(lambda who=who: create(world, who, kb_ids=[theirs]))
        assert (err.kind, err.reason) == (Kind.NOT_FOUND, "dataset_not_found"), "no owner or admin override of a private dataset"


@pytest.mark.parametrize("bad", ["not-an-id", "f" * 32, "A" * 32, 7])
def test_unknown_and_malformed_dataset_ids_are_dataset_not_found(world, bad):
    err = refused(lambda: create(world, world.a, kb_ids=[bad]))
    assert (err.kind, err.reason) == (Kind.NOT_FOUND, "dataset_not_found")


def test_a_dataset_of_another_workspace_is_dataset_not_found(world):
    foreign = dataset(world.outsider.tenant_id, world.outsider, "team")
    err = refused(lambda: create(world, world.a, kb_ids=[foreign]))
    assert (err.kind, err.reason) == (Kind.NOT_FOUND, "dataset_not_found")


def test_datasets_with_different_embedding_models_are_refused(world):
    one, two = dataset(world.tenant, world.a, "me", EMBED_A), dataset(world.tenant, world.a, "me", EMBED_B)
    err = refused(lambda: create(world, world.a, kb_ids=[one, two]))
    assert (err.kind, err.reason) == (Kind.INVALID, "embedding_mismatch")
    assert create(world, world.a, kb_ids=[one, one])["kb_ids"] == [one], "a repeated id is one dataset"


def test_the_chat_model_must_be_a_chat_model_of_the_workspace(world):
    for bad in (EMBED_A, RERANK_A, f"nothing@{PROVIDER}", "", "no-provider-part", "x" * 300, None):
        err = refused(lambda bad=bad: svc.create_assistant(world.principal(world.a), world.scope(world.a), {"name": unique_name("m"), "llm_id": bad}))
        assert (err.kind, err.reason) == (Kind.INVALID, "model_unavailable"), bad
    err = refused(lambda: svc.create_assistant(world.principal(world.a), world.scope(world.a), {"name": unique_name("m")}))
    assert err.reason == "model_unavailable", "the model is never chosen for the caller"
    assert create(world, world.a, llm_id=CHAT_B)["llm_id"] == CHAT_B


def test_the_rerank_model_must_be_a_rerank_model(world):
    for bad in (CHAT_A, EMBED_A, f"nothing@{PROVIDER}"):
        err = refused(lambda bad=bad: create(world, world.a, rerank_id=bad))
        assert (err.kind, err.reason) == (Kind.INVALID, "model_unavailable"), bad
    assert create(world, world.a, rerank_id=RERANK_A)["rerank_id"] == RERANK_A
    assert create(world, world.a)["rerank_id"] == "" and create(world, world.a, rerank_id=None)["rerank_id"] == ""


def test_a_model_of_another_workspace_is_not_available(world, llm, registry):
    lone = registry.register(prefix="dlnone")  # no models configured at all
    err = refused(lambda: svc.create_assistant(world.principal(lone), resolve_scope(world.principal(lone), None), body()))
    assert err.reason == "model_unavailable"


@pytest.mark.parametrize(
    "bad",
    [
        {"name": ""}, {"name": "   "}, {"name": "x" * 129}, {"name": 5}, {"permission": "everyone"}, {"permission": None}, {"top_n": 0}, {"top_n": 31},
        {"top_n": True}, {"top_n": 2.5}, {"similarity_threshold": 1.01}, {"similarity_threshold": -0.1}, {"vector_similarity_weight": 2},
        {"similarity_threshold": float("nan")}, {"llm_setting": {"temperature": 2.1}}, {"llm_setting": {"top_p": -0.1}},
        {"llm_setting": {"frequency_penalty": 2.5}}, {"llm_setting": {"presence_penalty": -3}}, {"llm_setting": {"max_tokens": 0}},
        {"llm_setting": {"max_tokens": 8193}}, {"llm_setting": {"max_tokens": 10.5}}, {"llm_setting": {"stop": ["x"]}}, {"llm_setting": "hot"},
        {"prompt_config": {"empty_response": ""}}, {"prompt_config": {"empty_response": "   "}}, {"prompt_config": {"empty_response": "x" * 501}},
        {"prompt_config": {"prologue": "x" * 501}}, {"prompt_config": {"system": "x" * 8001}}, {"prompt_config": {"parameters": []}},
        {"prompt_config": None}, {"kb_ids": ["a" * 32] * 21}, {"kb_ids": "all"}, {"unexpected": 1}, {"tenant_id": "x"}, {"created_by": "x"}, {"status": "0"},
    ],
)  # fmt: skip
def test_out_of_range_and_unknown_fields_are_refused_with_fields_invalid(world, bad):
    err = refused(lambda: create(world, world.a, **bad))
    assert (err.kind, err.reason) == (Kind.INVALID, "fields_invalid"), bad
    with DB.connection_context():
        assert Dialog.select().where(Dialog.tenant_id == world.tenant).count() == 0, "nothing was stored by the refused call"


def test_the_boundary_values_are_accepted(world):
    view = create(
        world, world.a, top_n=30, similarity_threshold=0, vector_similarity_weight=1,
        llm_setting={"temperature": 0, "top_p": 1, "frequency_penalty": -2, "presence_penalty": 2, "max_tokens": 8192},
        prompt_config={"system": "s" * 8000, "prologue": "", "empty_response": "e" * 500},
    )  # fmt: skip
    assert (view["top_n"], view["similarity_threshold"], view["vector_similarity_weight"]) == (30, 0.0, 1.0)
    assert view["llm_setting"]["max_tokens"] == 8192 and len(view["prompt_config"]["system"]) == 8000


def test_icon_must_be_a_png_or_jpeg_data_url_within_the_cap(world):
    jpeg = "data:image/jpeg;base64,/9j/4AAQSkZJRg=="
    assert create(world, world.a, icon=PNG)["icon"] == PNG
    assert create(world, world.a, icon=jpeg)["icon"] == jpeg
    assert create(world, world.a, icon="")["icon"] == "" and create(world, world.a, icon=None)["icon"] == ""
    big = "data:image/png;base64," + "A" * (400_000 - len("data:image/png;base64,"))
    assert create(world, world.a, icon=big)["icon"] == big
    for bad in (big + "A", "data:image/svg+xml;base64,PHN2Zz4=", "data:text/html;base64,PGI+", "https://example.test/a.png", "javascript:alert(1)", PNG + "<script>", 5):
        err = refused(lambda bad=bad: create(world, world.a, icon=bad))
        assert (err.kind, err.reason) == (Kind.INVALID, "fields_invalid"), str(bad)[:40]


# ----------------------------------------------------------------------------- read and list


def test_a_private_assistant_is_not_found_for_owner_admin_and_teammate_alike(world):
    view = create(world, world.a)
    chat_id = view["id"]
    missing = refused(lambda: get(world, world.a, uuid.uuid4().hex))
    for who in (world.owner, world.admin, world.b):
        err = refused(lambda who=who: get(world, who, chat_id))
        assert (err.kind, err.reason, err.message, err.data) == (missing.kind, missing.reason, missing.message, missing.data), "identical to a random id (D-19)"
        for call in (
            lambda who=who: svc.delete_assistant(world.principal(who), chat_id),
            lambda who=who: svc.resolve_for_chat(world.principal(who), chat_id),
            lambda who=who: svc.update_assistant(world.principal(who), chat_id, {"name": "taken over"}),
        ):
            err = refused(call)
            assert (err.kind, err.reason, err.message, err.data) == (missing.kind, missing.reason, missing.message, missing.data)
    assert stored(chat_id)["name"] == view["name"], "nobody else could change or remove it"


def test_a_malformed_foreign_or_unknown_chat_id_is_the_same_not_found(world):
    foreign = svc.create_assistant(world.principal(world.outsider), resolve_scope(world.principal(world.outsider), None), body(permission="team"))
    kinds = set()
    for chat_id in ("nope", "", "A" * 32, uuid.uuid4().hex, foreign["id"], None, 7):
        err = refused(lambda chat_id=chat_id: get(world, world.a, chat_id))
        kinds.add((err.kind, err.reason, err.message))
    assert kinds == {(Kind.NOT_FOUND, "assistant_not_found", "not found")}


def test_a_wasted_assistant_row_is_not_found(world):
    chat_id = create(world, world.a)["id"]
    with DB.connection_context():
        Dialog.update(status="0").where(Dialog.id == chat_id).execute()
    assert refused(lambda: get(world, world.a, chat_id)).kind is Kind.NOT_FOUND
    items, total = svc.list_assistants(world.principal(world.a), world.scope(world.a), 1, 20, None)
    assert total == 0 and items == []


def test_list_shows_the_callers_own_plus_team_assistants_only(world):
    mine = create(world, world.a, name="mine")["id"]
    shared = create(world, world.a, permission="team", name="shared")["id"]
    theirs_private = create(world, world.b, name="b-private")["id"]
    theirs_shared = create(world, world.b, permission="team", name="b-shared")["id"]
    expected = {
        world.a: {mine, shared, theirs_shared},
        world.b: {theirs_private, theirs_shared, shared},
        world.owner: {shared, theirs_shared},
        world.admin: {shared, theirs_shared},
    }
    for who, ids in expected.items():
        items, total = svc.list_assistants(world.principal(who), world.scope(who), 1, 50, None)
        assert {i["id"] for i in items} == ids and total == len(ids), who.nickname


def test_list_items_omit_icon_and_the_member_count_and_use_the_view_keys(world):
    create(world, world.a, icon=PNG, permission="team")
    items, _ = svc.list_assistants(world.principal(world.a), world.scope(world.a), 1, 20, None)
    assert len(items) == 1
    assert set(items[0]) == VIEW_KEYS - {"icon"} and not BANNED_KEYS & set(items[0])
    assert get(world, world.a, items[0]["id"])["icon"] == PNG


def test_list_is_newest_first_and_paginated_with_a_total(world):
    ids = [create(world, world.a, name=f"bot {n}")["id"] for n in range(5)]
    with DB.connection_context():
        for position, chat_id in enumerate(ids):
            Dialog.update(update_time=1_000 + position).where(Dialog.id == chat_id).execute()
    principal, scope = world.principal(world.a), world.scope(world.a)
    first, total = svc.list_assistants(principal, scope, 1, 2, None)
    second, _ = svc.list_assistants(principal, scope, 2, 2, None)
    last, _ = svc.list_assistants(principal, scope, 3, 2, None)
    assert total == 5
    assert [i["id"] for i in first + second + last] == list(reversed(ids))
    capped, _ = svc.list_assistants(principal, scope, 0, 10_000, None)
    assert len(capped) == 5, "an out-of-range page and size are clamped"


def test_list_keywords_match_names_and_wildcards_are_literal(world):
    plain = create(world, world.a, name="Release notes")["id"]
    percent = create(world, world.a, name="100% done")["id"]
    under = create(world, world.a, name="a_b")["id"]
    other = create(world, world.a, name="axb")["id"]
    principal, scope = world.principal(world.a), world.scope(world.a)

    def names(keyword: str) -> set[str]:
        return {i["id"] for i in svc.list_assistants(principal, scope, 1, 50, keyword)[0]}

    assert names("release") == {plain}
    assert names("%") == {percent}
    assert names("_") == {under}
    assert names("a_b") == {under}, "the underscore does not match any character"
    assert names("zzz") == set()
    assert names("") == {plain, percent, under, other}


def test_list_only_covers_the_acting_workspace(world):
    create(world, world.a, permission="team", name="in-owner-workspace")
    out_principal = world.principal(world.outsider)
    out_scope = resolve_scope(out_principal, None)
    svc.create_assistant(out_principal, out_scope, body(name="in-outsider-workspace", permission="team"))
    inside, _ = svc.list_assistants(world.principal(world.a), world.scope(world.a), 1, 20, None)
    outside, _ = svc.list_assistants(out_principal, out_scope, 1, 20, None)
    assert {i["name"] for i in inside} == {"in-owner-workspace"} and {i["name"] for i in outside} == {"in-outsider-workspace"}


def test_detail_kb_ids_hold_only_what_the_reader_can_open_and_the_count_matches(world):
    one, two = dataset(world.tenant, world.a, "team"), dataset(world.tenant, world.a, "team")
    chat_id = create(world, world.a, permission="team", kb_ids=[one, two])["id"]
    set_permission(two, "me")  # the creator's own dataset went private
    assert get(world, world.a, chat_id)["kb_ids"] == [one, two] and get(world, world.a, chat_id)["unavailable_datasets"] == 0
    for who in (world.b, world.admin, world.owner):
        seen = get(world, who, chat_id)
        assert seen["kb_ids"] == [one] and seen["unavailable_datasets"] == 1, who.nickname
    remove_dataset(one)
    assert get(world, world.a, chat_id)["kb_ids"] == [two] and get(world, world.a, chat_id)["unavailable_datasets"] == 1
    listed = {i["id"]: i for i in svc.list_assistants(world.principal(world.b), world.scope(world.b), 1, 20, None)[0]}
    assert listed[chat_id]["kb_ids"] == [] and listed[chat_id]["unavailable_datasets"] == 2


def test_the_list_reads_all_bound_datasets_of_the_page_in_one_query(world, monkeypatch):
    ds = dataset(world.tenant, world.a, "team")
    for n in range(4):
        create(world, world.a, permission="team", kb_ids=[ds], name=f"page {n}")
    calls: list[int] = []
    real = svc.live_datasets
    monkeypatch.setattr(svc, "live_datasets", lambda ids: (calls.append(1), real(ids))[1])
    items, _ = svc.list_assistants(world.principal(world.b), world.scope(world.b), 1, 20, None)
    assert len(items) == 4 and len(calls) == 1


def test_members_with_chats_counts_other_members_and_only_for_those_who_can_manage(world):
    chat_id = create(world, world.a, permission="team")["id"]
    session_of(chat_id, world.a)
    session_of(chat_id, world.a)
    assert get(world, world.a, chat_id)["members_with_chats"] == 0, "the viewer's own sessions are not counted"
    session_of(chat_id, world.b)
    session_of(chat_id, world.b)
    session_of(chat_id, world.admin)
    assert get(world, world.a, chat_id)["members_with_chats"] == 2
    assert get(world, world.admin, chat_id)["members_with_chats"] == 2, "the admin counts the creator and member b, not themselves"
    assert get(world, world.owner, chat_id)["members_with_chats"] == 3
    assert "members_with_chats" not in get(world, world.b, chat_id), "a member who cannot manage it does not see the count"


# ----------------------------------------------------------------------------- delete


def test_d26_deleting_a_team_assistant_removes_every_members_sessions(world):
    chat_id = create(world, world.a, permission="team")["id"]
    other = create(world, world.a, permission="team", name="untouched")["id"]
    for who in (world.a, world.b, world.b, world.admin):
        session_of(chat_id, who)
    kept = session_of(other, world.b)
    assert sessions(chat_id) == 4
    assert svc.delete_assistant(world.principal(world.a), chat_id) == chat_id
    assert sessions(chat_id) == 0 and stored(chat_id) is None, "the teammate's session rows went with it"
    with DB.connection_context():
        assert Conversation.get_or_none(Conversation.id == kept) is not None, "another assistant's sessions are untouched"
    assert refused(lambda: get(world, world.b, chat_id)).kind is Kind.NOT_FOUND


def test_an_ordinary_member_can_see_but_not_delete_a_team_assistant(world):
    chat_id = create(world, world.a, permission="team")["id"]
    err = refused(lambda: svc.delete_assistant(world.principal(world.b), chat_id))
    assert (err.kind, err.reason) == (Kind.FORBIDDEN, "forbidden")
    assert stored(chat_id) is not None


@pytest.mark.parametrize("deleter", ["owner", "admin"])
def test_owner_and_admin_may_delete_a_team_assistant(world, deleter):
    chat_id = create(world, world.a, permission="team")["id"]
    session_of(chat_id, world.b)
    assert svc.delete_assistant(world.principal(getattr(world, deleter)), chat_id) == chat_id
    assert stored(chat_id) is None and sessions(chat_id) == 0


def test_a_token_is_not_elevated_to_the_owner_or_admin_role(world):
    chat_id = create(world, world.a, permission="team")["id"]
    token_admin = world.principal(world.admin, auth=AUTH_API)
    token_admin = dataclasses.replace(token_admin, tenant_id=world.tenant, role="admin")
    err = refused(lambda: svc.delete_assistant(token_admin, chat_id))
    assert err.kind is Kind.FORBIDDEN, "the permission subject decides, never the role of the token's owner"
    assert stored(chat_id) is not None


def test_the_creator_deletes_a_private_assistant_and_a_repeat_is_not_found(world):
    chat_id = create(world, world.a)["id"]
    assert svc.delete_assistant(world.principal(world.a), chat_id) == chat_id
    assert refused(lambda: svc.delete_assistant(world.principal(world.a), chat_id)).kind is Kind.NOT_FOUND


def test_a_delete_that_fails_part_way_removes_neither_the_sessions_nor_the_assistant(world, monkeypatch):
    chat_id = create(world, world.a, permission="team")["id"]
    session_of(chat_id, world.b)
    real = Dialog.delete

    def boom(*args, **kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(Dialog, "delete", boom)
    with pytest.raises(RuntimeError):
        svc.delete_assistant(world.principal(world.a), chat_id)
    monkeypatch.setattr(Dialog, "delete", real)
    assert sessions(chat_id) == 1 and stored(chat_id) is not None, "one transaction: the cascade rolled back"


def test_delete_waits_for_the_row_lock_held_by_a_concurrent_writer(world):
    """The same ``FOR UPDATE`` that plan 05-09 takes when it creates a session serialises with a delete."""
    chat_id = create(world, world.a, permission="team")["id"]
    held, release, outcome = threading.Event(), threading.Event(), {}

    def holder() -> None:
        with DB.connection_context(), DB.atomic():
            Dialog.select(Dialog.id).where(Dialog.id == chat_id).for_update().first()
            held.set()
            release.wait(timeout=30)

    def deleter() -> None:
        outcome["id"] = svc.delete_assistant(world.principal(world.a), chat_id)

    first = threading.Thread(target=holder)
    first.start()
    assert held.wait(timeout=10)
    second = threading.Thread(target=deleter)
    second.start()

    def blocked() -> bool:
        conn = root_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM information_schema.innodb_trx WHERE trx_state = 'LOCK WAIT' AND trx_query LIKE '%`dialog`%'")
                return cur.fetchone()[0] > 0
        finally:
            conn.close()

    wait_until(blocked, timeout=15, interval=0.1)
    assert "id" not in outcome, "the delete is waiting on the row lock"
    release.set()
    first.join(timeout=30)
    second.join(timeout=30)
    assert outcome == {"id": chat_id} and stored(chat_id) is None


# ----------------------------------------------------------------------------- update


def update(world: World, who: Account, chat_id: str, **changes: Any) -> dict[str, Any]:
    return svc.update_assistant(world.principal(who), chat_id, changes)


def test_update_changes_only_the_fields_sent(world):
    team = dataset(world.tenant, world.a, "team")
    created = create(
        world, world.a, permission="team", kb_ids=[team], icon=PNG, rerank_id=RERANK_A, top_n=9,
        prompt_config={"system": "be brief", "prologue": "Hi", "empty_response": "none"}, llm_setting={"temperature": 1.0},
    )  # fmt: skip
    renamed = update(world, world.a, created["id"], name="Renamed")
    assert renamed["name"] == "Renamed"
    unchanged = {k: v for k, v in renamed.items() if k not in ("name", "update_time")}
    assert unchanged == {k: v for k, v in created.items() if k not in ("name", "update_time")}
    assert renamed["update_time"] >= created["update_time"]
    assert stored(created["id"])["kb_ids"] == [team]


def test_update_rejects_an_empty_body_unknown_fields_and_bad_values(world):
    chat_id = create(world, world.a)["id"]
    for bad in ({}, {"tenant_id": "x"}, {"created_by": world.b.user_id}, {"status": "0"}, {"top_n": 99}, {"name": ""}, {"name": None}, {"kb_ids": None}, {"prompt_config": {"empty_response": ""}}):
        err = refused(lambda bad=bad: svc.update_assistant(world.principal(world.a), chat_id, bad))
        assert (err.kind, err.reason) == (Kind.INVALID, "fields_invalid"), bad
    assert stored(chat_id)["name"] and stored(chat_id)["created_by"] == world.a.user_id


def test_update_partial_prompt_and_llm_settings_keep_the_stored_rest(world):
    chat_id = create(world, world.a, prompt_config={"system": "keep me", "prologue": "old"}, llm_setting={"temperature": 1.2, "max_tokens": 700})["id"]
    view = update(world, world.a, chat_id, prompt_config={"prologue": "new"}, llm_setting={"top_p": 0.9})
    assert view["prompt_config"]["system"] == "keep me" and view["prompt_config"]["prologue"] == "new"
    assert view["llm_setting"]["temperature"] == 1.2 and view["llm_setting"]["max_tokens"] == 700 and view["llm_setting"]["top_p"] == 0.9


def test_update_checks_uniqueness_case_insensitively_and_allows_the_own_name(world):
    create(world, world.a, name="Alpha")
    other = create(world, world.a, name="Beta")["id"]
    err = refused(lambda: update(world, world.a, other, name="ALPHA"))
    assert (err.kind, err.reason) == (Kind.CONFLICT, "duplicate_name")
    assert update(world, world.a, other, name="beta")["name"] == "beta", "a change of case on the own name is not a conflict"
    assert update(world, world.a, other, name="Beta")["name"] == "Beta"
    assert stored(other)["name"] == "Beta"


def test_update_model_checks_and_clearing_the_rerank_model(world):
    chat_id = create(world, world.a, rerank_id=RERANK_A)["id"]
    for field, bad in (("llm_id", EMBED_A), ("llm_id", RERANK_A), ("llm_id", f"x@{PROVIDER}"), ("llm_id", None), ("rerank_id", CHAT_A), ("rerank_id", f"x@{PROVIDER}")):
        err = refused(lambda field=field, bad=bad: svc.update_assistant(world.principal(world.a), chat_id, {field: bad}))
        assert (err.kind, err.reason) == (Kind.INVALID, "model_unavailable"), (field, bad)
    assert update(world, world.a, chat_id, llm_id=CHAT_B)["llm_id"] == CHAT_B
    assert update(world, world.a, chat_id, rerank_id=None)["rerank_id"] == ""
    assert update(world, world.a, chat_id, rerank_id=RERANK_A)["rerank_id"] == RERANK_A
    assert update(world, world.a, chat_id, rerank_id="")["rerank_id"] == ""


def test_update_of_other_fields_does_not_recheck_a_model_that_is_no_longer_configured(world, llm):
    chat_id = create(world, world.a)["id"]
    with DB.connection_context():
        Dialog.update(llm_id=f"gone@{PROVIDER}").where(Dialog.id == chat_id).execute()
    assert update(world, world.a, chat_id, top_n=5)["top_n"] == 5


def test_d24_who_may_edit_which_assistant(world):
    private = create(world, world.a, name="d24 private")["id"]
    shared = create(world, world.a, permission="team", name="d24 shared")["id"]
    # An ordinary member can use a team assistant but not edit it.
    err = refused(lambda: update(world, world.b, shared, top_n=3))
    assert (err.kind, err.reason) == (Kind.FORBIDDEN, "forbidden")
    # The creator edits both; the owner and the admin edit the team one.
    assert update(world, world.a, private, top_n=2)["top_n"] == 2
    assert update(world, world.a, shared, top_n=2)["top_n"] == 2
    assert update(world, world.admin, shared, top_n=3)["top_n"] == 3
    assert update(world, world.owner, shared, top_n=4)["top_n"] == 4
    # A private assistant is the creator's alone: owner and admin cannot even see it.
    for who in (world.owner, world.admin, world.b):
        err = refused(lambda who=who: update(world, who, private, top_n=9))
        assert err.kind is Kind.NOT_FOUND, who.nickname
    assert stored(shared) is not None and get(world, world.a, private)["top_n"] == 2


def test_d24_a_token_never_inherits_the_role_of_its_owner(world):
    shared = create(world, world.a, permission="team")["id"]
    token = dataclasses.replace(world.principal(world.admin, auth=AUTH_API), tenant_id=world.tenant, role="admin")
    err = refused(lambda: svc.update_assistant(token, shared, {"top_n": 3}))
    assert err.kind is Kind.FORBIDDEN


def test_d24_an_admin_who_narrows_a_team_assistant_gets_a_view_of_an_assistant_that_is_now_the_creators_alone(world):
    shared = create(world, world.a, permission="team")["id"]
    view = update(world, world.admin, shared, permission="me")
    assert view["permission"] == "me" and view["created_by"] == world.a.user_id
    assert "members_with_chats" not in view, "the admin can no longer manage it"
    assert refused(lambda: get(world, world.admin, shared)).kind is Kind.NOT_FOUND
    assert get(world, world.a, shared)["permission"] == "me"


def test_d23_narrowing_is_refused_while_another_member_has_a_session_and_nothing_is_deleted(world):
    shared = create(world, world.a, permission="team")["id"]
    session_of(shared, world.a)  # the creator's own sessions never block
    mine = session_of(shared, world.b)
    session_of(shared, world.b)  # two sessions of one member are one member
    err = refused(lambda: update(world, world.a, shared, permission="me"))
    assert (err.kind, err.reason, err.data) == (Kind.CONFLICT, "assistant_has_member_chats", {"count": 1})
    assert stored(shared)["permission"] == "team" and sessions(shared) == 3, "nothing was deleted or changed"
    session_of(shared, world.admin)
    err = refused(lambda: update(world, world.a, shared, permission="me", name="renamed too"))
    assert err.data == {"count": 2}
    assert stored(shared)["name"] != "renamed too", "the refused save changed nothing"
    # Once no other member has a session the switch succeeds.
    with DB.connection_context():
        Conversation.delete().where((Conversation.dialog_id == shared) & (Conversation.user_id != world.a.user_id)).execute()
    assert mine and update(world, world.a, shared, permission="me")["permission"] == "me"
    assert sessions(shared) == 1, "the creator's own session is kept"


def test_d23_an_admins_own_sessions_count_when_the_admin_narrows(world):
    shared = create(world, world.a, permission="team")["id"]
    session_of(shared, world.admin)
    err = refused(lambda: update(world, world.admin, shared, permission="me"))
    assert (err.reason, err.data) == ("assistant_has_member_chats", {"count": 1}), "only the creator is excluded"
    with DB.connection_context():
        Conversation.delete().where(Conversation.dialog_id == shared).execute()
    session_of(shared, world.a)
    assert update(world, world.admin, shared, permission="me")["permission"] == "me"


def test_d23_widening_to_team_has_no_session_condition(world):
    chat_id = create(world, world.a)["id"]
    session_of(chat_id, world.a)
    assert update(world, world.a, chat_id, permission="team")["permission"] == "team"


def test_d25_a_save_never_unbinds_a_dataset_the_saver_cannot_open(world):
    theirs, shared_ds, mine = dataset(world.tenant, world.a, "team"), dataset(world.tenant, world.owner, "team"), dataset(world.tenant, world.admin, "team")
    chat_id = create(world, world.a, permission="team", kb_ids=[theirs, shared_ds])["id"]
    set_permission(theirs, "me")  # the creator's dataset went private: the admin can no longer open it
    # Omitting kb_ids leaves the list alone; a save with kb_ids keeps what the admin cannot see.
    assert update(world, world.admin, chat_id, name="admin rename")["name"] == "admin rename"
    assert stored(chat_id)["kb_ids"] == [theirs, shared_ds]
    saved = update(world, world.admin, chat_id, kb_ids=[mine])
    assert saved["kb_ids"] == [mine], "the admin sees only what they can open"
    assert stored(chat_id)["kb_ids"] == [theirs, mine], "the hidden id is kept, the visible one replaced"
    assert get(world, world.a, chat_id)["kb_ids"] == [theirs, mine]
    update(world, world.admin, chat_id, kb_ids=[])
    assert stored(chat_id)["kb_ids"] == [theirs], "clearing removes only what the saver could see"


def test_d25_the_saver_cannot_choose_a_dataset_they_cannot_open(world):
    hidden = dataset(world.tenant, world.a, "me")
    shared = create(world, world.a, permission="team")["id"]
    err = refused(lambda: update(world, world.admin, shared, kb_ids=[hidden]))
    assert (err.kind, err.reason) == (Kind.NOT_FOUND, "dataset_not_found")
    err = refused(lambda: update(world, world.admin, shared, kb_ids=[dataset(world.outsider.tenant_id, world.outsider, "team")]))
    assert err.reason == "dataset_not_found"
    assert stored(shared)["kb_ids"] == []


def test_d25_a_deleted_dataset_is_dropped_by_the_next_save_that_sends_kb_ids(world):
    one, two = dataset(world.tenant, world.a, "team"), dataset(world.tenant, world.a, "team")
    chat_id = create(world, world.a, permission="team", kb_ids=[one, two])["id"]
    remove_dataset(one)
    assert update(world, world.a, chat_id, name="still bound")["unavailable_datasets"] == 1
    assert stored(chat_id)["kb_ids"] == [one, two]
    view = update(world, world.a, chat_id, kb_ids=[two])
    assert stored(chat_id)["kb_ids"] == [two] and view["unavailable_datasets"] == 0


def test_d25_embedding_models_of_the_requested_datasets_must_agree(world):
    one, two = dataset(world.tenant, world.a, "team", EMBED_A), dataset(world.tenant, world.a, "team", EMBED_B)
    chat_id = create(world, world.a, permission="team")["id"]
    err = refused(lambda: update(world, world.a, chat_id, kb_ids=[one, two]))
    assert (err.kind, err.reason) == (Kind.INVALID, "embedding_mismatch")


def test_d10_widening_to_team_is_refused_with_the_offenders_the_caller_can_open(world):
    private, team = dataset(world.tenant, world.a, "me"), dataset(world.tenant, world.a, "team")
    chat_id = create(world, world.a, kb_ids=[team, private])["id"]
    err = refused(lambda: update(world, world.a, chat_id, permission="team"))
    assert (err.kind, err.reason, err.data) == (Kind.CONFLICT, "assistant_dataset_not_shared", {"dataset_ids": [private]})
    assert stored(chat_id)["permission"] == "me"
    # Swapping to shared datasets in the same save is fine.
    assert update(world, world.a, chat_id, permission="team", kb_ids=[team])["permission"] == "team"


def test_d10_widening_counts_a_bound_dataset_the_saver_can_no_longer_open_without_naming_it(world):
    theirs = dataset(world.tenant, world.b, "team")
    chat_id = create(world, world.a, kb_ids=[theirs])["id"]
    set_permission(theirs, "me")  # b made it private: a no longer sees it
    err = refused(lambda: update(world, world.a, chat_id, permission="team"))
    assert (err.reason, err.data) == ("assistant_dataset_not_shared", {"dataset_ids": []}), "the id of a dataset the caller cannot open is not revealed"
    remove_dataset(theirs)
    assert update(world, world.a, chat_id, permission="team")["permission"] == "team", "a deleted dataset is ignored"


def test_d10_a_team_assistant_cannot_gain_a_private_dataset_but_keeps_the_ones_it_has(world):
    team, other = dataset(world.tenant, world.a, "team"), dataset(world.tenant, world.a, "team")
    private = dataset(world.tenant, world.a, "me")
    chat_id = create(world, world.a, permission="team", kb_ids=[team, other])["id"]
    err = refused(lambda: update(world, world.a, chat_id, kb_ids=[team, private]))
    assert (err.reason, err.data) == ("assistant_dataset_not_shared", {"dataset_ids": [private]})
    set_permission(other, "me")  # later it goes private: re-saving the same list is not "adding"
    assert update(world, world.a, chat_id, kb_ids=[team, other])["kb_ids"] == [team, other]
    assert stored(chat_id)["kb_ids"] == [team, other]


def test_a_private_assistant_may_gain_any_dataset_its_creator_can_open(world):
    private = dataset(world.tenant, world.a, "me")
    chat_id = create(world, world.a)["id"]
    assert update(world, world.a, chat_id, kb_ids=[private])["kb_ids"] == [private]


# ----------------------------------------------------------------------------- the chat-time dataset set


def test_resolve_for_chat_with_no_datasets_is_plain_chat(world):
    chat_id = create(world, world.a)["id"]
    binding = svc.resolve_for_chat(world.principal(world.a), chat_id)
    assert (binding.usable_dataset_ids, binding.unavailable_count, binding.tenant_id) == ((), 0, world.tenant)
    assert binding.assistant.id == chat_id and binding.assistant.llm_id == CHAT_A


def test_resolve_for_chat_is_decided_per_reader(world):
    own, shared = dataset(world.tenant, world.a, "team"), dataset(world.tenant, world.owner, "team")
    chat_id = create(world, world.a, permission="team", kb_ids=[own, shared])["id"]
    set_permission(own, "me")  # the assistant stays team; the dataset went private
    creator = svc.resolve_for_chat(world.principal(world.a), chat_id)
    assert (creator.usable_dataset_ids, creator.unavailable_count) == ((own, shared), 0), "its own creator keeps it"
    for who in (world.b, world.admin, world.owner):
        binding = svc.resolve_for_chat(world.principal(who), chat_id)
        assert (binding.usable_dataset_ids, binding.unavailable_count) == ((shared,), 1), who.nickname
        assert get(world, who, chat_id)["unavailable_datasets"] == binding.unavailable_count, "the notice matches what the answer skips"


def test_resolve_for_chat_skips_a_deleted_dataset_for_everyone(world):
    one, two = dataset(world.tenant, world.a, "team"), dataset(world.tenant, world.a, "team")
    chat_id = create(world, world.a, permission="team", kb_ids=[one, two])["id"]
    remove_dataset(one)
    for who in (world.a, world.b):
        binding = svc.resolve_for_chat(world.principal(who), chat_id)
        assert (binding.usable_dataset_ids, binding.unavailable_count) == ((two,), 1)


def test_resolve_for_chat_does_not_raise_when_nothing_is_usable(world):
    only = dataset(world.tenant, world.a, "team")
    chat_id = create(world, world.a, permission="team", kb_ids=[only])["id"]
    set_permission(only, "me")
    binding = svc.resolve_for_chat(world.principal(world.b), chat_id)
    assert (binding.usable_dataset_ids, binding.unavailable_count) == ((), 1), "the turn service refuses with datasets_unavailable"


def test_resolve_for_chat_for_a_private_assistant_is_the_creators_alone(world):
    mine = dataset(world.tenant, world.a, "me")
    chat_id = create(world, world.a, kb_ids=[mine])["id"]
    assert svc.resolve_for_chat(world.principal(world.a), chat_id).usable_dataset_ids == (mine,)
    assert refused(lambda: svc.resolve_for_chat(world.principal(world.admin), chat_id)).kind is Kind.NOT_FOUND


def test_resolve_for_chat_never_returns_a_dataset_of_another_workspace(world):
    foreign = dataset(world.outsider.tenant_id, world.outsider, "team")
    chat_id = create(world, world.a)["id"]
    with DB.connection_context():
        Dialog.update(kb_ids=[foreign]).where(Dialog.id == chat_id).execute()  # a corrupted row: the binding rule is re-applied at chat time
    binding = svc.resolve_for_chat(world.principal(world.a), chat_id)
    assert (binding.usable_dataset_ids, binding.unavailable_count) == ((), 1)


def test_an_update_waits_for_the_assistant_row_lock_so_a_session_creation_and_a_narrowing_serialise(world):
    shared = create(world, world.a, permission="team")["id"]
    held, release, outcome = threading.Event(), threading.Event(), {}

    def holder() -> None:
        # What plan 05-09 does when it creates a session: lock the assistant row, then insert the session.
        with DB.connection_context(), DB.atomic():
            Dialog.select(Dialog.id).where(Dialog.id == shared).for_update().first()
            held.set()
            release.wait(timeout=30)
            Conversation.create(id=uuid.uuid4().hex, dialog_id=shared, user_id=world.b.user_id, name="late", message=[], reference=[])

    def narrower() -> None:
        try:
            outcome["view"] = update(world, world.a, shared, permission="me")
        except ServiceError as exc:
            outcome["error"] = exc.reason

    first = threading.Thread(target=holder)
    first.start()
    assert held.wait(timeout=10)
    second = threading.Thread(target=narrower)
    second.start()

    def blocked() -> bool:
        conn = root_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM information_schema.innodb_trx WHERE trx_state = 'LOCK WAIT' AND trx_query LIKE '%`dialog`%'")
                return cur.fetchone()[0] > 0
        finally:
            conn.close()

    wait_until(blocked, timeout=15, interval=0.1)
    assert not outcome, "the narrowing is waiting for the lock"
    release.set()
    first.join(timeout=30)
    second.join(timeout=30)
    assert outcome == {"error": "assistant_has_member_chats"}, "the session that committed first is seen by the narrowing check"
    assert stored(shared)["permission"] == "team"
