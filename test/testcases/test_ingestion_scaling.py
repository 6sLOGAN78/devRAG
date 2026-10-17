"""Two executors and a graceful stop on the real containers (plan 04-22).

ING-16, DEPLOY-17, success criterion 5. The second executor comes from ``--scale task-executor=2`` with no other setting. The loopback provider is
the third party's end of the embedding wire. The module restores the default single executor in teardown. Waiting is polling with deadlines.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from common.settings import Settings, load_settings
from test.helpers import executor_control as ctl
from test.helpers.accounts import Account, AccountRegistry
from test.helpers.fake_provider import FakeProvider, running_stack_fake_provider
from test.helpers.ingest import chunk_texts, index_count, paragraphs, start_parse, task_rows, task_state, upload_text, wait_run
from test.helpers.wait import wait_until
from test.testcases.conftest import BASE_URL
from test.testcases.test_dataset_flow import create, workspace
from test.testcases.test_provider_flow import api, ok

pytestmark = [pytest.mark.e2e, pytest.mark.serial]

CHUNKS = 40
DOCS = 6


@pytest.fixture(scope="module")
def executors() -> Iterator[list[str]]:
    try:
        yield ctl.use_fast_executors(2)
    finally:
        ctl.restore_default_executor()
        ids = ctl.container_ids()
        assert len(ids) == 1 and ctl.is_healthy(ids[0])


@pytest.fixture(scope="module")
def fake() -> Iterator[FakeProvider]:
    with running_stack_fake_provider() as provider:
        yield provider


@pytest.fixture(autouse=True)
def clean_provider(fake: FakeProvider, executors: list[str]) -> Iterator[None]:
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
    return workspace(ingress, registry, fake, "scale")


@pytest.fixture(scope="module")
def settings() -> Settings:
    return load_settings()


def live_consumers(settings: Settings, containers: list[str]) -> list[dict[str, Any]]:
    """Group consumers that belong to one of the running ``containers`` (consumers of earlier, removed containers stay listed by Valkey)."""
    return [c for c in ctl.consumers(settings) if ctl.container_of(str(c["name"])) in containers]


def test_two_executors_share_six_documents_with_one_attempt_each(
    ingress: httpx.Client, owner: Account, settings: Settings, executors: list[str]
) -> None:
    names = wait_until(
        lambda: (lambda found: found if len(found) == 2 else None)(live_consumers(settings, executors)),
        timeout=60, interval=1.0, describe=lambda: "both executors never registered as consumers of the group",
    )  # fmt: skip
    assert len({c["name"] for c in names}) == 2

    dataset_id = ok(create(ingress, owner))["id"]
    docs = [upload_text(ingress, owner, dataset_id, paragraphs(3), f"scale{i}.txt") for i in range(DOCS)]
    resp = start_parse(ingress, owner, dataset_id, [d["id"] for d in docs])
    assert resp.status_code == 200, resp.text
    for doc in docs:
        row = wait_run(ingress, owner, dataset_id, doc["id"], "3", timeout=180)
        assert row["chunk_count"] == 3 == index_count(settings, owner.tenant_id, dataset_id, doc["id"])
        listed = [c["id"] for c in chunk_texts(api, ingress, owner.token, dataset_id, doc["id"])]
        assert len(listed) == len(set(listed)) == 3
        (task_id,) = task_rows(doc["id"])
        assert task_state(task_id)["retry_count"] == 1, "one attempt each"
    wait_until(
        lambda: ctl.pending_entries(settings) == [] and all(int(c["pending"]) == 0 for c in live_consumers(settings, executors)),
        timeout=60, interval=1.0, describe=lambda: "an entry is still pending",
    )  # fmt: skip


def test_a_graceful_stop_hands_the_running_task_on_and_refunds_the_attempt(
    ingress: httpx.Client, owner: Account, fake: FakeProvider, settings: Settings, executors: list[str]
) -> None:
    dataset_id = ok(create(ingress, owner))["id"]
    doc = upload_text(ingress, owner, dataset_id, paragraphs(CHUNKS))
    fake.delay_ms = 300
    assert start_parse(ingress, owner, dataset_id, [doc["id"]]).status_code == 200
    wait_until(lambda: 2 <= index_count(settings, owner.tenant_id, dataset_id, doc["id"]) < CHUNKS, timeout=90, interval=0.2, describe=lambda: "the parse never got part-way")
    victim = wait_until(lambda: ctl.container_of(ctl.pending_owner(settings)), timeout=30, interval=0.2, describe=lambda: "no container owns the task")
    assert victim in executors
    assert ctl.stop(victim) == 0, "the stopped executor exits with status 0"

    row = wait_run(ingress, owner, dataset_id, doc["id"], "3", timeout=180)
    assert row["chunk_count"] == CHUNKS == index_count(settings, owner.tenant_id, dataset_id, doc["id"])
    listed = [c["id"] for c in chunk_texts(api, ingress, owner.token, dataset_id, doc["id"])]
    assert len(listed) == len(set(listed)) and set(listed) == {f"{doc['id']}_{i}" for i in range(CHUNKS)}
    (task_id,) = task_rows(doc["id"])
    assert task_state(task_id)["retry_count"] == 1, "the stopped attempt was refunded"
    wait_until(lambda: ctl.pending_entries(settings) == [], timeout=60, interval=1.0, describe=lambda: "an entry is still pending")
