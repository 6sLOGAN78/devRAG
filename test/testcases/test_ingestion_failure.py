"""Crash, reclaim, poison, cancel, partial failure and re-parse on the real executor containers (plan 04-22).

ING-05, ING-11, ING-12, D-03, D-05..D-09, D-25, D-30, success criterion 4, E2E-05. Nothing of devRag is replaced: the loopback provider is the third
party's end of the embedding wire, slowed or switched to refuse only through its own knobs. The module recreates the executor service with the
short-timing override and restores the default single executor in teardown. Waiting is polling with deadlines.
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from common.ingest_codes import PLAIN_MESSAGES
from common.settings import Settings, load_settings
from test.helpers import executor_control as ctl
from test.helpers.accounts import Account, AccountRegistry
from test.helpers.fake_provider import FakeProvider, running_stack_fake_provider
from test.helpers.ingest import (
    chunk_texts,
    doc_row,
    index_count,
    paragraphs,
    poison_docx,
    start_parse,
    task_rows,
    task_state,
    upload_text,
    wait_run,
)
from test.helpers.uploads import sql
from test.helpers.wait import wait_until
from test.testcases.conftest import BASE_URL
from test.testcases.test_dataset_flow import create, workspace
from test.testcases.test_provider_flow import api, ok

pytestmark = [pytest.mark.e2e, pytest.mark.serial]

CHUNKS = 40
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
BANNED = ("Traceback", "/ragflow", "/tmp", "host.docker.internal", "127.0.0.1", 'File "')
KEY_SHAPE = re.compile(r"\bsk-[A-Za-z0-9]")


def leaks(text: str) -> list[str]:
    found = [b for b in BANNED if b in text]
    if KEY_SHAPE.search(text):
        found.append("key shape")
    return found


@pytest.fixture(scope="module")
def executors() -> Iterator[list[str]]:
    try:
        yield ctl.use_fast_executors(2)
    finally:
        ctl.restore_default_executor()
        assert len(ctl.container_ids()) == 1 and ctl.is_healthy(ctl.container_ids()[0])


@pytest.fixture(scope="module")
def fake() -> Iterator[FakeProvider]:
    with running_stack_fake_provider() as provider:
        yield provider


@pytest.fixture(autouse=True)
def clean_provider(fake: FakeProvider) -> Iterator[None]:
    fake.delay_ms, fake.embed_mode = 0, "ok"
    fake.reset()
    yield
    fake.delay_ms, fake.embed_mode = 0, "ok"


@pytest.fixture(scope="module")
def registry(ingress: httpx.Client) -> Iterator[AccountRegistry]:
    accounts = AccountRegistry(BASE_URL)
    try:
        yield accounts
    finally:
        accounts.cleanup()


@pytest.fixture(scope="module")
def owner(ingress: httpx.Client, registry: AccountRegistry, fake: FakeProvider) -> Account:
    return workspace(ingress, registry, fake, "fail")


@pytest.fixture(scope="module")
def settings() -> Settings:
    return load_settings()


def new_dataset(ingress: httpx.Client, who: Account) -> str:
    return ok(create(ingress, who))["id"]


def ids_in_index(ingress: httpx.Client, who: Account, dataset_id: str, doc_id: str) -> list[str]:
    return [c["id"] for c in chunk_texts(api, ingress, who.token, dataset_id, doc_id)]


def expected_ids(doc_id: str) -> set[str]:
    return {f"{doc_id}_{i}" for i in range(CHUNKS)}


def logs_path(dataset_id: str, log_id: str | None = None) -> str:
    base = f"/api/v1/datasets/{dataset_id}/ingestions"
    return base if log_id is None else f"{base}/{log_id}"


def latest_log(ingress: httpx.Client, who: Account, dataset_id: str, doc_id: str) -> dict[str, Any]:
    items = ok(api(ingress, "GET", logs_path(dataset_id), who.token, params={"size": "100"}))["items"]
    mine = [i for i in items if i["document_id"] == doc_id]
    assert mine, "the run never reached the log"
    return mine[0]


def pending_for_doc(settings: Settings, doc_id: str) -> list[str]:
    tasks = set(task_rows(doc_id))
    client = ctl.stream_client(settings)
    try:
        found = []
        for entry in ctl.pending_entries(settings):
            for _, fields in client.xrange(ctl.stream_name(settings), entry["message_id"], entry["message_id"]):
                if any(t in str(fields) for t in tasks):
                    found.append(entry["message_id"])
        return found
    finally:
        client.close()


# ----------------------------------------------------------------------------- a killed worker


def test_kill_mid_task_is_reclaimed_and_completes_with_exact_chunks(
    ingress: httpx.Client, owner: Account, fake: FakeProvider, settings: Settings, executors: list[str]
) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(CHUNKS))
    fake.delay_ms = 300
    assert start_parse(ingress, owner, dataset_id, [doc["id"]]).status_code == 200

    def underway() -> bool:
        (task_id,) = task_rows(doc["id"])
        return index_count(settings, owner.tenant_id, dataset_id, doc["id"]) >= 2 and task_state(task_id)["progress"] < 1

    wait_until(underway, timeout=90, interval=0.2, describe=lambda: "the parse never got under way")
    victim = wait_until(
        lambda: ctl.container_of(ctl.pending_owner(settings)), timeout=30, interval=0.2, describe=lambda: "no container owns the pending task"
    )
    assert index_count(settings, owner.tenant_id, dataset_id, doc["id"]) < CHUNKS, "the task finished before the kill"
    killed_at = time.monotonic()
    ctl.kill(victim)
    row = wait_run(ingress, owner, dataset_id, doc["id"], "3", timeout=180)
    seconds = time.monotonic() - killed_at
    print(f"kill to finished: {seconds:.1f} s")  # noqa: T201  (measured value recorded in the SUMMARY)

    assert row["chunk_count"] == CHUNKS == index_count(settings, owner.tenant_id, dataset_id, doc["id"])
    listed = ids_in_index(ingress, owner, dataset_id, doc["id"])
    assert len(listed) == len(set(listed)) == CHUNKS, "no duplicate chunk ids"
    assert set(listed) == expected_ids(doc["id"]), "none missing"
    (task_id,) = task_rows(doc["id"])
    manifest = str(sql("SELECT `chunk_ids` FROM `task` WHERE `id` = %s", (task_id,))[0][0] or "").split()
    assert set(manifest) == set(listed), "the task manifest equals the index"
    attempts = task_state(task_id)["retry_count"]
    assert attempts in (2, 3), f"one killed attempt and one completing attempt, below the cap; saw {attempts}"
    wait_until(lambda: pending_for_doc(settings, doc["id"]) == [], timeout=60, interval=1.0, describe=lambda: "a stream entry is still pending")


# ----------------------------------------------------------------------------- a poison file


def test_poison_a_truncated_docx_fails_after_three_attempts_with_a_plain_reason(
    ingress: httpx.Client, owner: Account, fake: FakeProvider, settings: Settings, executors: list[str]
) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, poison_docx(), "damaged.docx", mime=DOCX)
    fake.reset()
    began = time.time()
    assert start_parse(ingress, owner, dataset_id, [doc["id"]]).status_code == 200
    row = wait_run(ingress, owner, dataset_id, doc["id"], "4", timeout=120)
    (task_id,) = task_rows(doc["id"])
    state = task_state(task_id)
    assert state["retry_count"] == 3 and state["progress"] == -1

    wait_until(
        lambda: any(i["document_id"] == doc["id"] and i["result"] == "failed" for i in ok(api(ingress, "GET", logs_path(dataset_id), owner.token))["items"]),
        timeout=60, interval=1.0, describe=lambda: "the failed run never reached the log",
    )  # fmt: skip
    entry_resp = api(ingress, "GET", logs_path(dataset_id, latest_log(ingress, owner, dataset_id, doc["id"])["id"]), owner.token)
    entry = ok(entry_resp)
    assert (entry["attempts"], entry["retried"]) == (3, True)
    assert entry["error"]["code"] == "file_damaged" and entry["error"]["message"] == PLAIN_MESSAGES["file_damaged"]

    assert fake.hits("/v1/embeddings") == [], "the provider received no embedding request for the damaged file"
    status = api(ingress, "GET", f"/v1/task/status/{task_id}", owner.token)
    for text in (str(row), entry_resp.text, status.text):
        assert leaks(text) == [], (leaks(text), text[:300])
    for cid in ctl.container_ids():
        assert leaks(ctl.logs_since(cid, began)) == [], f"internals in the executor log of {cid[:12]}"
