"""Chunk list, add, edit and switch end to end on the running stack (plan 04-18; CHUNK-16, CHUNK-18..21, IDX-07, KB-19, BE-06, E2E-05, D-10..D-12, D-26).

Nothing of devRag is replaced: Nginx, the app, the task executor, MySQL, MinIO, Valkey and Elasticsearch are the running stack. The loopback provider is
the third party's end of the embedding wire; its ``embed_mode`` makes it refuse, never answer or rate-limit. Index rows are read from the host.
"""
from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from common.doc_store.doc_store_base import index_name
from common.settings import Settings, load_settings
from rag.utils.es_conn import get_doc_store
from test.helpers.accounts import Account, AccountRegistry
from test.helpers.fake_provider import FakeProvider, running_stack_fake_provider
from test.helpers.ingest import dataset_row, doc_row, paragraphs, start_parse, thirteen_page_pdf, upload_text, wait_run
from test.testcases.conftest import BASE_URL
from test.testcases.test_dataset_flow import create, workspace
from test.testcases.test_provider_flow import NOT_FOUND, TOKENS, _bearer, api, join, ok

pytestmark = pytest.mark.e2e

FORBIDDEN = {"code": 403, "message": "forbidden", "data": None}
LONG = 200
EXPECTED_ITEM_KEYS = {"id", "text", "positions", "origin", "enabled"}


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
    return workspace(ingress, registry, fake, "chunk")


@pytest.fixture(scope="module")
def settings() -> Settings:
    return load_settings()


@pytest.fixture(autouse=True)
def _provider_answers(fake: FakeProvider) -> Iterator[None]:
    fake.embed_mode = "ok"
    fake.delay_ms = 0
    yield
    fake.embed_mode = "ok"
    fake.delay_ms = 0


# ----------------------------------------------------------------------------- helpers


def new_dataset(ingress: httpx.Client, who: Account, **body: object) -> str:
    return ok(create(ingress, who, **body))["id"]


def parsed(ingress: httpx.Client, who: Account, count: int, **dataset: object) -> SimpleNamespace:
    """A dataset and a TXT document of ``count`` chunks, parsed and finished."""
    dataset_id = new_dataset(ingress, who, **dataset)
    doc = upload_text(ingress, who, dataset_id, paragraphs(count))
    resp = start_parse(ingress, who, dataset_id, [doc["id"]])
    assert resp.status_code == 200, resp.text
    row = wait_run(ingress, who, dataset_id, doc["id"], "3", timeout=120)
    assert row["chunk_count"] == count
    return SimpleNamespace(dataset_id=dataset_id, doc_id=doc["id"])


def chunks_path(dataset_id: str, doc_id: str, chunk_id: str | None = None) -> str:
    base = f"/api/v1/datasets/{dataset_id}/documents/{doc_id}/chunks"
    return base if chunk_id is None else f"{base}/{chunk_id}"


def read(ingress: httpx.Client, who: Account, where: SimpleNamespace, **params: object) -> httpx.Response:
    return api(ingress, "GET", chunks_path(where.dataset_id, where.doc_id), who.token, params={k: str(v) for k, v in params.items()})


def items_of(ingress: httpx.Client, who: Account, where: SimpleNamespace, **params: object) -> list[dict[str, Any]]:
    return ok(read(ingress, who, where, **{"size": 100, **params}))["items"]


def add(ingress: httpx.Client, who: Account, where: SimpleNamespace, text: object, **extra: object) -> httpx.Response:
    return api(ingress, "POST", chunks_path(where.dataset_id, where.doc_id), who.token, body={"content_with_weight": text, **extra})


def patch(ingress: httpx.Client, who: Account, where: SimpleNamespace, chunk_id: str, body: dict[str, object]) -> httpx.Response:
    return api(ingress, "PATCH", chunks_path(where.dataset_id, where.doc_id, chunk_id), who.token, body=body)


def reason_of(resp: httpx.Response) -> object:
    return (resp.json().get("data") or {}).get("reason")


def stored(settings: Settings, owner: Account, where: SimpleNamespace, chunk_id: str) -> dict[str, Any]:
    found = get_doc_store(settings).get(chunk_id, index_name(owner.tenant_id), [where.dataset_id])
    assert found is not None
    return found


# ----------------------------------------------------------------------------- list


def test_a_parsed_text_document_lists_forty_chunks_in_order_twenty_at_a_time(ingress: httpx.Client, owner: Account) -> None:
    where = parsed(ingress, owner, 40)
    first = ok(read(ingress, owner, where))
    assert first["total"] == 40 and len(first["items"]) == 20 and first["page_sizes"] == {}
    assert all(set(item) == EXPECTED_ITEM_KEYS for item in first["items"])
    assert [item["text"][:8] for item in first["items"]] == [f"para{i:04d}" for i in range(20)]
    assert all(item["origin"] == "parsed" and item["enabled"] is True and item["positions"] == [] for item in first["items"])
    second = ok(read(ingress, owner, where, page=2))
    assert [item["text"][:8] for item in second["items"]] == [f"para{i:04d}" for i in range(20, 40)]
    assert len(ok(read(ingress, owner, where, size=100))["items"]) == 40
    for bad in ({"size": 101}, {"size": 0}, {"page": 0}, {"available": 2}, {"size": "x"}, {"keywords": "k" * 129}):
        resp = read(ingress, owner, where, **bad)
        assert resp.status_code == 400 and reason_of(resp) == "query_invalid", (bad, resp.text)


def test_a_parsed_pdf_lists_positions_on_pages_one_to_thirteen_with_page_sizes(ingress: httpx.Client, owner: Account) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, thirteen_page_pdf(), "thirteen.pdf", mime="application/pdf")
    assert start_parse(ingress, owner, dataset_id, [doc["id"]]).status_code == 200
    wait_run(ingress, owner, dataset_id, doc["id"], "3", timeout=180)
    data = ok(read(ingress, owner, SimpleNamespace(dataset_id=dataset_id, doc_id=doc["id"]), size=100))
    boxes = [box for item in data["items"] for box in item["positions"]]
    assert {box["page"] for box in boxes} == set(range(1, 14))
    assert all(set(box) == {"page", "x0", "top", "x1", "bottom"} and box["x1"] >= box["x0"] and box["bottom"] >= box["top"] for box in boxes)
    assert set(data["page_sizes"]) == {str(p) for p in range(1, 14)}
    assert all(len(size) == 2 and size[0] > 0 and size[1] > 0 for size in data["page_sizes"].values())


def test_keywords_filter_and_odd_text_is_a_list_not_an_error(ingress: httpx.Client, owner: Account) -> None:
    where = parsed(ingress, owner, 12)
    found = ok(read(ingress, owner, where, keywords="para0007"))
    assert found["total"] == 1 and found["items"][0]["text"].startswith("para0007")
    for odd in ("what is (revenue", '"unclosed', "a AND OR", "((", "*", "x:y"):
        resp = read(ingress, owner, where, keywords=odd)
        assert resp.status_code == 200 and isinstance(resp.json()["data"]["items"], list), (odd, resp.text)


# ----------------------------------------------------------------------------- add, edit, re-parse


def test_add_edit_and_reparse_keep_the_counts_and_ask_before_replacing(ingress: httpx.Client, owner: Account, settings: Settings) -> None:
    where = parsed(ingress, owner, 6)
    listed = items_of(ingress, owner, where)
    target = listed[3]

    made = ok(add(ingress, owner, where, "  my own note about revenue  "))
    assert made["origin"] == "manual" and made["text"] == "my own note about revenue" and made["positions"] == [] and made["enabled"] is True
    after_add = items_of(ingress, owner, where)
    assert len(after_add) == 7 and after_add[-1]["id"] == made["id"], "the hand-made chunk is last"
    assert doc_row(ingress, owner, where.dataset_id, where.doc_id)["chunk_count"] == 7
    assert dataset_row(ingress, owner, where.dataset_id)["chunk_num"] == 7

    before = stored(settings, owner, where, target["id"])
    changed = ok(patch(ingress, owner, where, target["id"], {"content_with_weight": "edited text about margins"}))
    assert changed["origin"] == "edited" and changed["text"] == "edited text about margins" and changed["id"] == target["id"]
    after = stored(settings, owner, where, target["id"])
    assert after["content_with_weight"] == "edited text about margins" and after["content_ltks"] == "edited text about margins"
    vector = next(k for k in after if k.endswith("_vec"))
    assert after[vector] != before[vector], "the vector was replaced together with the text"
    assert after["order_int"] == before["order_int"]

    refused = start_parse(ingress, owner, where.dataset_id, [where.doc_id])
    assert refused.status_code == 409 and reason_of(refused) == "confirm_required", refused.text
    entry = refused.json()["data"]["documents"][0]
    assert entry["edited_count"] == 1 and entry["manual_count"] == 1 and entry["chunk_count"] == 7

    assert start_parse(ingress, owner, where.dataset_id, [where.doc_id], confirm=True).status_code == 200
    wait_run(ingress, owner, where.dataset_id, where.doc_id, "3", timeout=120)
    again = items_of(ingress, owner, where)
    assert len(again) == 6 and {i["origin"] for i in again} == {"parsed"}, "a confirmed re-parse ends with the original count"
    assert dataset_row(ingress, owner, where.dataset_id)["chunk_num"] == 6


@pytest.mark.parametrize(("mode", "statuses", "reason"), [("refuse", {400}, "provider_refused"), ("ratelimit", {429, 503}, "provider_rate_limited")])
def test_a_provider_that_refuses_or_limits_changes_nothing_and_never_looks_like_a_login_failure(
    ingress: httpx.Client, owner: Account, fake: FakeProvider, settings: Settings, mode: str, statuses: set[int], reason: str
) -> None:
    where = parsed(ingress, owner, 4)
    target = items_of(ingress, owner, where)[1]
    before = stored(settings, owner, where, target["id"])
    fake.embed_mode = mode
    resp = patch(ingress, owner, where, target["id"], {"content_with_weight": "never stored"})
    assert resp.status_code in statuses and reason_of(resp) == reason and resp.status_code != 401, resp.text
    refused_add = add(ingress, owner, where, "never stored either")
    assert refused_add.status_code in statuses and reason_of(refused_add) == reason, refused_add.text
    assert stored(settings, owner, where, target["id"]) == before, "text and vector are byte for byte as they were"
    listed = items_of(ingress, owner, where)
    assert len(listed) == 4 and listed[1]["text"] == target["text"]
    assert doc_row(ingress, owner, where.dataset_id, where.doc_id)["chunk_count"] == 4
    fake.embed_mode = "ok"
    assert ok(patch(ingress, owner, where, target["id"], {"content_with_weight": "now it works"}))["text"] == "now it works"


def test_a_provider_that_never_answers_is_a_timeout_and_the_old_text_stays(ingress: httpx.Client, owner: Account, fake: FakeProvider, settings: Settings) -> None:
    where = parsed(ingress, owner, 3)
    target = items_of(ingress, owner, where)[1]
    before = stored(settings, owner, where, target["id"])
    fake.embed_mode = "timeout"
    resp = patch(ingress, owner, where, target["id"], {"content_with_weight": "never stored"})
    assert resp.status_code in {502, 504} and reason_of(resp) == "provider_timeout", resp.text
    assert stored(settings, owner, where, target["id"]) == before
    assert items_of(ingress, owner, where)[1]["text"] == target["text"]


# ----------------------------------------------------------------------------- the chunk's own switch (D-26)


def test_a_chunk_switched_off_stays_off_after_its_document_is_switched_off_and_on(ingress: httpx.Client, owner: Account) -> None:
    where = parsed(ingress, owner, 4)
    listed = items_of(ingress, owner, where)
    off = ok(patch(ingress, owner, where, listed[2]["id"], {"available": False}))
    assert off["enabled"] is False and off["origin"] == "parsed" and off["text"] == listed[2]["text"]
    assert [i["id"] for i in items_of(ingress, owner, where, available=0)] == [listed[2]["id"]]
    assert len(items_of(ingress, owner, where, available=1)) == 3

    status = f"/api/v1/datasets/{where.dataset_id}/documents/batch-update-status"
    assert api(ingress, "POST", status, owner.token, body={"doc_ids": [where.doc_id], "status": "0"}).status_code == 200
    assert api(ingress, "POST", status, owner.token, body={"doc_ids": [where.doc_id], "status": "1"}).status_code == 200
    assert [i["id"] for i in items_of(ingress, owner, where, available=0)] == [listed[2]["id"]], "the document switch did not turn the chunk back on"
    assert [i["enabled"] for i in items_of(ingress, owner, where)] == [True, True, False, True]


def test_chunk_writes_are_refused_while_the_document_is_parsing(ingress: httpx.Client, owner: Account, fake: FakeProvider) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(LONG))
    where = SimpleNamespace(dataset_id=dataset_id, doc_id=doc["id"])
    fake.delay_ms = 2000
    try:
        assert start_parse(ingress, owner, dataset_id, [doc["id"]]).status_code == 200
        posted = add(ingress, owner, where, "while parsing")
        assert posted.status_code == 409 and reason_of(posted) == "parse_running", posted.text
        patched = patch(ingress, owner, where, f"{doc['id']}_0", {"available": False})
        assert patched.status_code == 409 and reason_of(patched) == "parse_running", patched.text
        assert read(ingress, owner, where).status_code == 200, "reading is allowed while parsing"
        assert start_parse(ingress, owner, dataset_id, [doc["id"]], run="2").status_code == 200
    finally:
        fake.delay_ms = 0


# ----------------------------------------------------------------------------- who may do what


def test_members_read_but_only_the_uploader_creator_and_owner_write(ingress: httpx.Client, registry: AccountRegistry, owner: Account) -> None:
    alice, bob = registry.register(prefix="chal"), registry.register(prefix="chbo")
    join(ingress, owner, alice)
    join(ingress, owner, bob)
    team = new_dataset(ingress, owner, permission="team")
    doc = upload_text(ingress, alice, team, paragraphs(3))
    assert start_parse(ingress, alice, team, [doc["id"]]).status_code == 200
    wait_run(ingress, owner, team, doc["id"], "3", timeout=120)
    where = SimpleNamespace(dataset_id=team, doc_id=doc["id"])
    first = items_of(ingress, bob, where)[0]

    assert read(ingress, bob, where).status_code == 200, "a plain member reads"
    for resp in (add(ingress, bob, where, "x"), patch(ingress, bob, where, first["id"], {"available": False}), patch(ingress, bob, where, first["id"], {"content_with_weight": "x"})):
        assert resp.status_code == 403 and resp.json() == FORBIDDEN, resp.text
    assert items_of(ingress, owner, where)[0]["enabled"] is True and len(items_of(ingress, owner, where)) == 3

    assert add(ingress, alice, where, "by the uploader").status_code == 200
    assert patch(ingress, owner, where, first["id"], {"available": False}).status_code == 200

    ingress.cookies.clear()
    owner_token = ingress.post(TOKENS, headers=_bearer(owner.token))
    holder = Account(owner.email, owner.password, owner.nickname, owner.user_id, owner.tenant_id, owner_token.json()["data"]["token"])
    assert patch(ingress, holder, where, first["id"], {"available": True}).status_code == 200, "the owner's token acts as its subject (the dataset's creator)"


def test_bad_text_unknown_fields_foreign_ids_and_private_datasets(ingress: httpx.Client, registry: AccountRegistry, owner: Account) -> None:
    where = parsed(ingress, owner, 3)
    other = SimpleNamespace(dataset_id=where.dataset_id, doc_id=upload_text(ingress, owner, where.dataset_id, paragraphs(2))["id"])
    first = items_of(ingress, owner, where)[0]

    too_long = add(ingress, owner, where, "x" * 32001)
    assert too_long.status_code == 400 and reason_of(too_long) == "chunk_too_long", too_long.text
    assert add(ingress, owner, where, "   ").status_code == 400
    assert add(ingress, owner, where, "ok", sneaky=1).status_code == 400
    assert patch(ingress, owner, where, first["id"], {}).status_code == 400
    assert patch(ingress, owner, where, first["id"], {"available": False, "origin": "manual"}).status_code == 400
    assert len(items_of(ingress, owner, where)) == 3

    other_doc_chunk = f"{other.doc_id}_0"
    for bad in (other_doc_chunk, "not-a-chunk", f"{where.doc_id}_m_zz", f"{where.doc_id}_999999", "0" * 32 + "_0"):
        resp = patch(ingress, owner, where, bad, {"available": False})
        assert resp.status_code == 404 and resp.json() == NOT_FOUND, (bad, resp.text)
    foreign_doc = api(ingress, "GET", chunks_path(where.dataset_id, "0" * 32), owner.token)
    assert foreign_doc.status_code == 404 and foreign_doc.json() == NOT_FOUND

    member = registry.register(prefix="chpri")
    join(ingress, owner, member)
    private = parsed(ingress, owner, 2, permission="me")
    for resp in (read(ingress, member, private), add(ingress, member, private, "x"), patch(ingress, member, private, f"{private.doc_id}_0", {"available": False})):
        assert resp.status_code == 404 and resp.json() == NOT_FOUND, resp.text
