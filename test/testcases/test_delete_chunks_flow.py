"""Deleting a document or a dataset removes what it indexed, end to end on the running stack (plan 04-17; IDX-14, R-136, D-10).

Chunks, task rows and pipeline log rows are checked from the host. A worker that is still writing when the document is deleted stops and leaves no
orphan chunk (PATTERNS gotchas 25 and 26). Waiting is polling with a deadline.
"""
from __future__ import annotations

import time
from collections.abc import Iterator

import httpx
import pytest

from common.settings import Settings, load_settings
from test.helpers.accounts import Account, AccountRegistry
from test.helpers.fake_provider import FakeProvider, running_stack_fake_provider
from test.helpers.ingest import dataset_row, index_count, paragraphs, start_parse, task_rows, upload_text, wait_run
from test.helpers.uploads import sql
from test.helpers.wait import wait_until
from test.testcases.conftest import BASE_URL
from test.testcases.test_dataset_flow import create, workspace
from test.testcases.test_provider_flow import _bearer, ok

pytestmark = pytest.mark.e2e

CHUNKS = 6
LONG = 200


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
    return workspace(ingress, registry, fake, "delch")


@pytest.fixture(scope="module")
def settings() -> Settings:
    return load_settings()


def new_dataset(ingress: httpx.Client, who: Account) -> str:
    return ok(create(ingress, who))["id"]


def parsed(ingress: httpx.Client, who: Account, dataset_id: str, count: int = CHUNKS) -> str:
    doc = upload_text(ingress, who, dataset_id, paragraphs(count))
    assert start_parse(ingress, who, dataset_id, [doc["id"]]).status_code == 200
    wait_run(ingress, who, dataset_id, doc["id"], "3", timeout=120)
    return doc["id"]


def remove_documents(ingress: httpx.Client, who: Account, dataset_id: str, ids: list[str]) -> httpx.Response:
    ingress.cookies.clear()
    return ingress.request("DELETE", f"/api/v1/datasets/{dataset_id}/documents", headers=_bearer(who.token), json={"ids": ids}, timeout=60.0)


def log_rows(doc_id: str) -> int:
    return int(sql("SELECT COUNT(*) FROM `pipeline_operation_log` WHERE `document_id` = %s", (doc_id,))[0][0])


def test_delete_removes_chunks_tasks_and_log_rows_and_lowers_the_counters(ingress: httpx.Client, owner: Account, settings: Settings) -> None:
    dataset_id = new_dataset(ingress, owner)
    gone, kept = parsed(ingress, owner, dataset_id), parsed(ingress, owner, dataset_id, 4)
    assert task_rows(gone) and log_rows(gone) >= 1
    before = dataset_row(ingress, owner, dataset_id)
    assert before["chunk_num"] == CHUNKS + 4
    tokens_of_gone = int(sql("SELECT `token_num` FROM `document` WHERE `id` = %s", (gone,))[0][0])

    resp = remove_documents(ingress, owner, dataset_id, [gone])
    assert resp.status_code == 200 and resp.json()["data"] == {"deleted": 1}, resp.text
    assert index_count(settings, owner.tenant_id, dataset_id, gone) == 0
    assert task_rows(gone) == [] and log_rows(gone) == 0
    after = dataset_row(ingress, owner, dataset_id)
    assert after["chunk_num"] == 4 and after["token_num"] == before["token_num"] - tokens_of_gone
    assert index_count(settings, owner.tenant_id, dataset_id, kept) == 4 and task_rows(kept)


def test_deleting_while_a_parse_runs_leaves_no_orphan_chunk(ingress: httpx.Client, owner: Account, fake: FakeProvider, settings: Settings) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(LONG))
    fake.delay_ms = 1500
    try:
        assert start_parse(ingress, owner, dataset_id, [doc["id"]]).status_code == 200
        wait_until(lambda: index_count(settings, owner.tenant_id, dataset_id, doc["id"]) > 0, timeout=90, interval=1.0, describe=lambda: "no chunk was indexed")
        resp = remove_documents(ingress, owner, dataset_id, [doc["id"]])
        assert resp.status_code == 200, resp.text
    finally:
        fake.delay_ms = 0
    state = {"count": -1, "since": time.monotonic()}

    def settled() -> bool:
        now_count = index_count(settings, owner.tenant_id, dataset_id, doc["id"])
        if now_count != state["count"]:
            state.update(count=now_count, since=time.monotonic())
            return False
        return now_count == 0 and time.monotonic() - state["since"] >= 8

    wait_until(settled, timeout=120, interval=1.0, describe=lambda: f"chunks of the deleted document remain: {state['count']}")
    assert index_count(settings, owner.tenant_id, dataset_id, doc["id"]) == 0
    assert task_rows(doc["id"]) == [] and log_rows(doc["id"]) == 0


def test_deleting_a_dataset_leaves_the_other_datasets_chunks_in_the_same_index(ingress: httpx.Client, owner: Account, settings: Settings) -> None:
    doomed, spared = new_dataset(ingress, owner), new_dataset(ingress, owner)
    doomed_doc, spared_doc = parsed(ingress, owner, doomed), parsed(ingress, owner, spared, 5)
    ingress.cookies.clear()
    resp = ingress.request("DELETE", "/api/v1/datasets", headers=_bearer(owner.token), json={"ids": [doomed]}, timeout=120.0)
    assert resp.status_code == 200, resp.text
    assert index_count(settings, owner.tenant_id, doomed, doomed_doc) == 0
    assert index_count(settings, owner.tenant_id, spared, spared_doc) == 5
    assert int(sql("SELECT COUNT(*) FROM `document` WHERE `kb_id` = %s", (doomed,))[0][0]) == 0
    assert task_rows(doomed_doc) == [] and log_rows(doomed_doc) == 0
    assert int(sql("SELECT COUNT(*) FROM `pipeline_operation_log` WHERE `kb_id` = %s", (doomed,))[0][0]) == 0


def test_the_executor_logs_no_traceback_for_these_runs(started_at: float) -> None:
    from test.helpers.executor_control import container_ids, logs_since  # the container name changes whenever the service is recreated

    ids = container_ids()
    assert ids, "no task-executor container is running"
    assert all("Traceback" not in logs_since(cid, started_at) for cid in ids)
