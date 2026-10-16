"""Parse, cancel and re-parse end to end on the real stack (plan 04-14; DOC-09..11, ING-12, KB-19, E2E-05, D-01..D-04, D-06, D-09, D-13, D-15).

Nothing of devRag is replaced: Nginx, the app, the task-executor container, MySQL, MinIO, Valkey and Elasticsearch are the running stack. The loopback
provider is only the third party's end of the embedding wire. Chunk counts are exact because ``paragraphs(n)`` makes n paragraphs of 300 tokens each,
and the default budget of 512 tokens holds one of them. Waiting is polling with a deadline.
"""
from __future__ import annotations

import subprocess
import time
from collections.abc import Iterator
from types import SimpleNamespace

import httpx
import pytest

from test.helpers.accounts import Account, AccountRegistry
from test.helpers.fake_provider import FakeProvider, running_stack_fake_provider
from test.helpers.ingest import (
    dataset_row,
    doc_row,
    index_count,
    paragraphs,
    start_parse,
    task_rows,
    upload_text,
    wait_run,
)
from test.helpers.wait import wait_until
from test.testcases.conftest import BASE_URL, DOCKER, PROJECT
from test.testcases.test_dataset_flow import create, workspace
from test.testcases.test_provider_flow import NOT_FOUND, TOKENS, _bearer, join, ok
from common.settings import load_settings

pytestmark = pytest.mark.e2e

CHUNKS = 40
LONG = 200  # four batches of 64, so a slow provider leaves time to cancel between them
FORBIDDEN = {"code": 403, "message": "forbidden", "data": None}
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 64


def reason_of(resp: httpx.Response) -> object:
    return (resp.json().get("data") or {}).get("reason")


@pytest.fixture(scope="module")
def started_at() -> float:
    return time.time()


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
    return workspace(ingress, registry, fake, "parse")


@pytest.fixture(scope="module")
def settings():
    return load_settings()


def new_dataset(ingress: httpx.Client, who: Account, **body: object) -> str:
    return ok(create(ingress, who, **body))["id"]


@pytest.fixture(scope="module")
def finished(ingress: httpx.Client, owner: Account, settings) -> SimpleNamespace:
    """One document uploaded, parsed and finished in a dataset of its own; the first count and the parse answer are kept."""
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(CHUNKS))
    resp = start_parse(ingress, owner, dataset_id, [doc["id"]])
    assert resp.status_code == 200, f"parse answered {resp.status_code}: {resp.text[:200]}"
    row = wait_run(ingress, owner, dataset_id, doc["id"], "3", timeout=120)
    return SimpleNamespace(dataset_id=dataset_id, doc_id=doc["id"], answer=resp, row=row, count=index_count(settings, owner.tenant_id, dataset_id, doc["id"]))


# ----------------------------------------------------------------------------- the journey


def test_an_upload_parses_nothing(ingress: httpx.Client, owner: Account) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(CHUNKS))
    row = doc_row(ingress, owner, dataset_id, doc["id"])
    assert row["run"] == "0" and row["progress"] == 0 and row["chunk_num"] == 0
    assert task_rows(doc["id"]) == [], "no task row exists until a parse request names the document (D-01)"


def test_parse_takes_a_document_from_not_started_to_finished_with_the_index_as_truth(ingress: httpx.Client, owner: Account, finished: SimpleNamespace, settings) -> None:
    assert finished.answer.status_code == 200, finished.answer.text
    started = finished.answer.json()["data"]["started"]
    assert [s["id"] for s in started] == [finished.doc_id]
    row = finished.row
    assert row["run"] == "3" and row["progress"] == 1
    assert finished.count == CHUNKS and row["chunk_num"] == finished.count, "the document counter equals the index"
    assert row["token_num"] > 0
    dataset = dataset_row(ingress, owner, finished.dataset_id)
    assert dataset["chunk_num"] == finished.count and dataset["token_num"] == row["token_num"]


def test_parsing_a_finished_document_needs_a_confirmation_and_changes_nothing(ingress: httpx.Client, owner: Account, finished: SimpleNamespace, settings) -> None:
    before_row = doc_row(ingress, owner, finished.dataset_id, finished.doc_id)
    resp = start_parse(ingress, owner, finished.dataset_id, [finished.doc_id])
    assert resp.status_code == 409 and reason_of(resp) == "confirm_required", resp.text
    entry = resp.json()["data"]["documents"][0]
    assert entry["chunk_count"] == finished.count and entry["edited_count"] == 0 and entry["manual_count"] == 0
    assert doc_row(ingress, owner, finished.dataset_id, finished.doc_id) == before_row
    assert index_count(settings, owner.tenant_id, finished.dataset_id, finished.doc_id) == finished.count


def test_a_confirmed_reparse_replaces_the_chunks_and_ends_with_the_same_count(ingress: httpx.Client, owner: Account, finished: SimpleNamespace, settings) -> None:
    resp = start_parse(ingress, owner, finished.dataset_id, [finished.doc_id], confirm=True)
    assert resp.status_code == 200, resp.text
    row = wait_run(ingress, owner, finished.dataset_id, finished.doc_id, "3", timeout=120)
    assert row["progress"] == 1 and row["chunk_num"] == finished.count
    assert index_count(settings, owner.tenant_id, finished.dataset_id, finished.doc_id) == finished.count


def test_cancel_keeps_the_indexed_chunks_and_a_following_parse_finishes_without_a_dialog(ingress: httpx.Client, owner: Account, fake: FakeProvider, settings) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(LONG))
    fake.delay_ms = 2000
    try:
        assert start_parse(ingress, owner, dataset_id, [doc["id"]]).status_code == 200
        wait_until(lambda: index_count(settings, owner.tenant_id, dataset_id, doc["id"]) > 0, timeout=90, interval=1.0, describe=lambda: "no chunk was indexed")
        resp = start_parse(ingress, owner, dataset_id, [doc["id"]], run="2")
        assert resp.status_code == 200 and resp.json()["data"] == {"cancelled": [doc["id"]]}, resp.text
        assert doc_row(ingress, owner, dataset_id, doc["id"])["run"] == "2"
    finally:
        fake.delay_ms = 0

    state = {"count": -1, "since": time.monotonic()}

    def stable() -> bool:
        now_count = index_count(settings, owner.tenant_id, dataset_id, doc["id"])
        if now_count != state["count"]:
            state.update(count=now_count, since=time.monotonic())
            return False
        return time.monotonic() - state["since"] >= 6

    wait_until(stable, timeout=90, interval=1.0, describe=lambda: "the count never settled")
    kept = state["count"]
    assert 0 < kept < LONG, "chunks indexed before the cancel stay, the rest are never made"
    assert doc_row(ingress, owner, dataset_id, doc["id"])["run"] == "2"

    again = start_parse(ingress, owner, dataset_id, [doc["id"]])
    assert again.status_code == 200, "nothing was edited, so no dialog is needed after a cancel"
    row = wait_run(ingress, owner, dataset_id, doc["id"], "3", timeout=180)
    assert row["chunk_num"] == LONG == index_count(settings, owner.tenant_id, dataset_id, doc["id"])


# ----------------------------------------------------------------------------- who may parse


def test_only_the_uploader_the_creator_and_the_owner_may_parse(ingress: httpx.Client, registry: AccountRegistry, owner: Account) -> None:
    alice, bob = registry.register(prefix="parali"), registry.register(prefix="parbob")
    join(ingress, owner, alice)
    join(ingress, owner, bob)
    team = new_dataset(ingress, owner, permission="team")
    mine = upload_text(ingress, alice, team, paragraphs(3))
    forbidden = start_parse(ingress, bob, team, [mine["id"]])
    assert forbidden.status_code == 403 and forbidden.json() == FORBIDDEN, forbidden.text
    assert task_rows(mine["id"]) == [] and doc_row(ingress, owner, team, mine["id"])["run"] == "0"
    allowed = start_parse(ingress, alice, team, [mine["id"]])
    assert allowed.status_code == 200, allowed.text
    wait_run(ingress, owner, team, mine["id"], "3", timeout=120)


def test_an_api_token_of_the_owner_parses_as_its_subject(ingress: httpx.Client, owner: Account) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(3))
    created = ingress.post(TOKENS, headers=_bearer(owner.token))
    assert created.status_code == 200, created.text
    holder = Account(owner.email, owner.password, owner.nickname, owner.user_id, owner.tenant_id, created.json()["data"]["token"])
    resp = start_parse(ingress, holder, dataset_id, [doc["id"]])
    assert resp.status_code == 200, resp.text
    wait_run(ingress, owner, dataset_id, doc["id"], "3", timeout=120)


# ----------------------------------------------------------------------------- refusals


def test_a_file_type_that_cannot_be_parsed_is_400_parse_unavailable(ingress: httpx.Client, owner: Account) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, PNG, "picture.png", mime="image/png")
    resp = start_parse(ingress, owner, dataset_id, [doc["id"]])
    assert resp.status_code == 400 and reason_of(resp) == "parse_unavailable", resp.text
    assert task_rows(doc["id"]) == [] and doc_row(ingress, owner, dataset_id, doc["id"])["run"] == "0"


def test_a_chunking_method_that_is_not_built_is_400_chunker_unavailable(ingress: httpx.Client, owner: Account) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(3), params={"parser_id": "qa"})
    resp = start_parse(ingress, owner, dataset_id, [doc["id"]])
    assert resp.status_code == 400 and reason_of(resp) == "chunker_unavailable", resp.text
    assert task_rows(doc["id"]) == []


def test_a_document_that_is_running_is_409_already_running(ingress: httpx.Client, owner: Account, fake: FakeProvider) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(LONG))
    fake.delay_ms = 2000
    try:
        assert start_parse(ingress, owner, dataset_id, [doc["id"]]).status_code == 200
        resp = start_parse(ingress, owner, dataset_id, [doc["id"]], confirm=True)
        assert resp.status_code == 409 and reason_of(resp) == "already_running", resp.text
        assert start_parse(ingress, owner, dataset_id, [doc["id"]], run="2").status_code == 200
    finally:
        fake.delay_ms = 0
    assert doc_row(ingress, owner, dataset_id, doc["id"])["run"] == "2"


def test_one_bad_id_starts_nothing_for_any_id(ingress: httpx.Client, owner: Account) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(3))
    resp = start_parse(ingress, owner, dataset_id, [doc["id"], "0" * 32])
    assert resp.status_code == 404 and resp.json() == NOT_FOUND, resp.text
    assert task_rows(doc["id"]) == [] and doc_row(ingress, owner, dataset_id, doc["id"])["run"] == "0"


def test_malformed_ids_and_too_many_ids_are_400_ids_invalid(ingress: httpx.Client, owner: Account) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(3))
    for ids in (["not-an-id"], [doc["id"], "x" * 300], [], [f"{i:032x}" for i in range(101)]):
        resp = start_parse(ingress, owner, dataset_id, ids)
        assert resp.status_code == 400 and reason_of(resp) == "ids_invalid", (len(ids), resp.text)
    assert task_rows(doc["id"]) == []


def test_an_outsider_and_an_absent_dataset_get_the_same_404(ingress: httpx.Client, registry: AccountRegistry, owner: Account) -> None:
    stranger = registry.register(prefix="parstr")
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(3))
    for who, target in [(stranger, dataset_id), (owner, "0" * 32), (owner, "not-an-id")]:
        resp = start_parse(ingress, who, target, [doc["id"]])
        assert resp.status_code == 404 and resp.json() == NOT_FOUND, (who.email, target, resp.text)
    assert task_rows(doc["id"]) == []


def test_unknown_fields_and_values_in_the_body_are_refused(ingress: httpx.Client, owner: Account) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(3))
    headers = {"Authorization": f"Bearer {owner.token}"}
    path = f"/api/v1/datasets/{dataset_id}/documents/parse"
    for body in ({"doc_ids": [doc["id"]], "run": "1", "priority": 9}, {"doc_ids": [doc["id"]], "run": "7"}):
        ingress.cookies.clear()
        resp = ingress.post(path, headers=headers, json=body)
        assert resp.status_code == 400, resp.text
    assert task_rows(doc["id"]) == []


def test_the_executor_logs_no_traceback_for_these_runs(started_at: float) -> None:
    out = subprocess.run(
        [DOCKER, "logs", "--since", str(int(started_at)), f"{PROJECT}-task-executor-1"], capture_output=True, text=True, check=False, timeout=60
    )
    assert out.returncode == 0, out.stderr[:200]
    assert "Traceback" not in out.stdout + out.stderr
