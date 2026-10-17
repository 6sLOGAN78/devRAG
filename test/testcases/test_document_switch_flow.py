"""The document search switch end to end on the running stack (plan 04-17; DOC-13, KB-19, E2E-05, D-26, R-163).

The route stores the switch in ``document.status`` and writes ``doc_enabled_int`` on every chunk. A parse that starts while the switch is off, or
one that is still running when it is switched off, ends with every chunk off. Chunk flags are read from Elasticsearch on the host.
"""
from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest

from common.doc_store.doc_store_base import index_name
from common.settings import Settings, load_settings
from rag.utils.es_conn import get_doc_store
from test.helpers.accounts import Account, AccountRegistry
from test.helpers.doc_store_contract import search
from test.helpers.fake_provider import FakeProvider, running_stack_fake_provider
from test.helpers.ingest import doc_row, index_count, paragraphs, start_parse, upload_text, wait_run
from test.helpers.wait import wait_until
from test.testcases.conftest import BASE_URL
from test.testcases.test_dataset_flow import create, workspace
from test.testcases.test_provider_flow import _bearer, join, ok

pytestmark = pytest.mark.e2e

CHUNKS = 6
LONG = 200
FORBIDDEN = {"code": 403, "message": "forbidden", "data": None}
NOT_FOUND = {"code": 404, "message": "not found", "data": None}


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
    return workspace(ingress, registry, fake, "swflow")


@pytest.fixture(scope="module")
def settings() -> Settings:
    return load_settings()


def new_dataset(ingress: httpx.Client, who: Account, **body: object) -> str:
    return ok(create(ingress, who, **body))["id"]


def switch(ingress: httpx.Client, who: Account, dataset_id: str, body: dict) -> httpx.Response:
    ingress.cookies.clear()
    return ingress.post(f"/api/v1/datasets/{dataset_id}/documents/batch-update-status", headers=_bearer(who.token), json=body, timeout=60.0)


def chunk_flags(settings: Settings, tenant_id: str, dataset_id: str, doc_id: str) -> list[int]:
    result = search(get_doc_store(settings), index_name(tenant_id), [dataset_id], condition={"doc_id": [doc_id]}, select=["doc_enabled_int"], limit=500)
    return sorted(int(h["doc_enabled_int"]) for h in result.hits)


def parsed(ingress: httpx.Client, who: Account, dataset_id: str, count: int = CHUNKS) -> str:
    doc = upload_text(ingress, who, dataset_id, paragraphs(count))
    assert start_parse(ingress, who, dataset_id, [doc["id"]]).status_code == 200
    wait_run(ingress, who, dataset_id, doc["id"], "3", timeout=120)
    return doc["id"]


def test_off_then_on_changes_every_chunk_and_the_list_row(ingress: httpx.Client, owner: Account, settings: Settings) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc_id = parsed(ingress, owner, dataset_id)
    assert chunk_flags(settings, owner.tenant_id, dataset_id, doc_id) == [1] * CHUNKS
    resp = switch(ingress, owner, dataset_id, {"doc_ids": [doc_id], "status": "0"})
    assert resp.status_code == 200 and resp.json()["data"] == {"updated": [doc_id], "enabled": False}, resp.text
    assert doc_row(ingress, owner, dataset_id, doc_id)["enabled"] is False
    assert chunk_flags(settings, owner.tenant_id, dataset_id, doc_id) == [0] * CHUNKS
    resp = switch(ingress, owner, dataset_id, {"doc_ids": [doc_id], "status": "1"})
    assert resp.status_code == 200 and resp.json()["data"] == {"updated": [doc_id], "enabled": True}, resp.text
    assert doc_row(ingress, owner, dataset_id, doc_id)["enabled"] is True
    assert chunk_flags(settings, owner.tenant_id, dataset_id, doc_id) == [1] * CHUNKS


def test_the_catalogue_body_shapes_switch_the_same_document(ingress: httpx.Client, owner: Account, settings: Settings) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc_id = parsed(ingress, owner, dataset_id, 3)
    for body in ({"doc_id": doc_id, "status": "0"}, {"doc_id": [doc_id], "status": "1"}, {"doc_id": doc_id, "doc_ids": [doc_id], "status": "0"}):
        resp = switch(ingress, owner, dataset_id, body)
        assert resp.status_code == 200 and resp.json()["data"]["updated"] == [doc_id], (body, resp.text)
    assert chunk_flags(settings, owner.tenant_id, dataset_id, doc_id) == [0] * 3


def test_bodies_without_ids_with_extra_keys_or_a_bad_status_are_400(ingress: httpx.Client, owner: Account) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(2))
    for body in ({"status": "0"}, {"doc_ids": [doc["id"]], "status": "0", "extra": 1}, {"doc_ids": [doc["id"]], "status": "2"}, {"doc_ids": [], "status": "0"}):
        assert switch(ingress, owner, dataset_id, body).status_code == 400, body
    assert switch(ingress, owner, dataset_id, {"doc_ids": ["nope"], "status": "0"}).status_code == 400
    assert doc_row(ingress, owner, dataset_id, doc["id"])["enabled"] is True


def test_a_parse_started_while_the_switch_is_off_ends_with_every_chunk_off(ingress: httpx.Client, owner: Account, settings: Settings) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(CHUNKS))
    assert switch(ingress, owner, dataset_id, {"doc_ids": [doc["id"]], "status": "0"}).status_code == 200
    assert start_parse(ingress, owner, dataset_id, [doc["id"]]).status_code == 200
    wait_run(ingress, owner, dataset_id, doc["id"], "3", timeout=120)
    assert chunk_flags(settings, owner.tenant_id, dataset_id, doc["id"]) == [0] * CHUNKS


def test_switching_off_in_the_middle_of_a_parse_ends_with_every_chunk_off(ingress: httpx.Client, owner: Account, fake: FakeProvider, settings: Settings) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(LONG))
    fake.delay_ms = 1500
    try:
        assert start_parse(ingress, owner, dataset_id, [doc["id"]]).status_code == 200
        wait_until(lambda: index_count(settings, owner.tenant_id, dataset_id, doc["id"]) > 0, timeout=90, interval=1.0, describe=lambda: "no chunk was indexed")
        assert switch(ingress, owner, dataset_id, {"doc_ids": [doc["id"]], "status": "0"}).status_code == 200
    finally:
        fake.delay_ms = 0
    wait_run(ingress, owner, dataset_id, doc["id"], "3", timeout=240)
    flags = chunk_flags(settings, owner.tenant_id, dataset_id, doc["id"])
    assert len(flags) == LONG and set(flags) == {0}


def test_only_the_uploader_the_creator_and_the_owner_may_switch(ingress: httpx.Client, registry: AccountRegistry, owner: Account) -> None:
    alice, bob = registry.register(prefix="swali"), registry.register(prefix="swbob")
    join(ingress, owner, alice)
    join(ingress, owner, bob)
    team = new_dataset(ingress, owner, permission="team")
    mine = upload_text(ingress, alice, team, paragraphs(2))
    denied = switch(ingress, bob, team, {"doc_ids": [mine["id"]], "status": "0"})
    assert denied.status_code == 403 and denied.json() == FORBIDDEN, denied.text
    assert doc_row(ingress, owner, team, mine["id"])["enabled"] is True
    assert switch(ingress, alice, team, {"doc_ids": [mine["id"]], "status": "0"}).status_code == 200
    assert switch(ingress, owner, team, {"doc_ids": [mine["id"]], "status": "1"}).status_code == 200


def test_an_outsider_and_one_foreign_id_get_the_one_404_and_change_nothing(ingress: httpx.Client, registry: AccountRegistry, owner: Account) -> None:
    outsider = registry.register(prefix="swout")
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(2))
    gone = switch(ingress, outsider, dataset_id, {"doc_ids": [doc["id"]], "status": "0"})
    assert gone.status_code == 404 and gone.json() == NOT_FOUND, gone.text
    mixed = switch(ingress, owner, dataset_id, {"doc_ids": [doc["id"], "0" * 32], "status": "0"})
    assert mixed.status_code == 404 and mixed.json() == NOT_FOUND, mixed.text
    assert doc_row(ingress, owner, dataset_id, doc["id"])["enabled"] is True
