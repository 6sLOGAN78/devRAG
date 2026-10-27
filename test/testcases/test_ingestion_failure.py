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
from test.testcases.test_chunk_flow import patch as patch_chunk
from test.testcases.test_chunk_flow import stored
from test.testcases.test_dataset_flow import create, workspace
from test.testcases.test_document_flow import delete_docs
from test.testcases.test_provider_flow import api, ok

pytestmark = [pytest.mark.e2e, pytest.mark.serial]

CHUNKS = 40
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
BANNED = ("Traceback", "/ragflow", "/tmp", "host.docker.internal", "127.0.0.1", 'File "')  # noqa: S108 - forbidden leak text, not a filesystem path used by this test
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


# ----------------------------------------------------------------------------- shared steps for cancel, failure and re-parse


def where_of(dataset_id: str, doc_id: str) -> SimpleNamespace:
    return SimpleNamespace(dataset_id=dataset_id, doc_id=doc_id)


def stays(read: Any, expected: Any, polls: int = 3, timeout: float = 60.0) -> None:
    """``read()`` equals ``expected`` for ``polls`` consecutive polls, one second apart."""
    state = {"run": 0}

    def check() -> bool:
        state["run"] = state["run"] + 1 if read() == expected else 0
        return state["run"] >= polls

    wait_until(check, timeout=timeout, interval=1.0, describe=lambda: f"never stayed at {expected!r} for {polls} polls")


def count_of(settings: Settings, who: Account, dataset_id: str, doc_id: str) -> int:
    return index_count(settings, who.tenant_id, dataset_id, doc_id)


def finish(ingress: httpx.Client, who: Account, settings: Settings, dataset_id: str, doc_id: str, *, confirm: bool = False) -> None:
    """Parse, wait for ``run 3`` and check the exact id set."""
    resp = start_parse(ingress, who, dataset_id, [doc_id], confirm=confirm)
    assert resp.status_code == 200, resp.text
    row = wait_run(ingress, who, dataset_id, doc_id, "3", timeout=180)
    assert row["chunk_count"] == CHUNKS == count_of(settings, who, dataset_id, doc_id)
    listed = ids_in_index(ingress, who, dataset_id, doc_id)
    assert len(listed) == len(set(listed)) and set(listed) == expected_ids(doc_id)


def midway(settings: Settings, who: Account, dataset_id: str, doc_id: str, low: int = 2) -> int:
    """Wait until between ``low`` and CHUNKS-1 chunks are indexed (the replaced chunks of a re-parse are gone first); returns the count seen."""
    return wait_until(
        lambda: (lambda n: n if low <= n < CHUNKS else 0)(count_of(settings, who, dataset_id, doc_id)),
        timeout=120, interval=0.1, describe=lambda: "the parse never got part-way",
    )  # fmt: skip


def cancel_midway(ingress: httpx.Client, who: Account, fake: FakeProvider, settings: Settings, dataset_id: str, doc_id: str) -> float:
    """Cancel a running slowed parse (``fake.delay_ms`` set by the caller) part-way and wait for the count to settle. Returns seconds to ``run 2``."""
    midway(settings, who, dataset_id, doc_id)
    began = time.monotonic()
    resp = start_parse(ingress, who, dataset_id, [doc_id], run="2")
    assert resp.status_code == 200 and resp.json()["data"] == {"cancelled": [doc_id]}, resp.text
    wait_until(lambda: doc_row(ingress, who, dataset_id, doc_id)["run"] == "2", timeout=5, interval=0.1, describe=lambda: "the row never said run 2")
    seconds = time.monotonic() - began
    fake.delay_ms = 0
    wait_settled(settings, who, dataset_id, doc_id)
    return seconds


def wait_settled(settings: Settings, who: Account, dataset_id: str, doc_id: str) -> int:
    """The index count once it stopped changing for three polls."""
    last = {"count": -1, "run": 0}

    def check() -> bool:
        now = count_of(settings, who, dataset_id, doc_id)
        last["run"] = last["run"] + 1 if now == last["count"] else 0
        last["count"] = now
        return last["run"] >= 3

    wait_until(check, timeout=90, interval=1.0, describe=lambda: "the chunk count never settled")
    return last["count"]


def fail_midway(ingress: httpx.Client, who: Account, fake: FakeProvider, settings: Settings, dataset_id: str, doc_id: str, *, confirm: bool = False) -> set[str]:
    """Parse with slowed embeddings, flip the provider to refuse after chunks were indexed, wait for ``run 4``. Returns the ids seen at the flip."""
    fake.delay_ms = 300
    resp = start_parse(ingress, who, dataset_id, [doc_id], confirm=confirm)
    assert resp.status_code == 200, resp.text
    midway(settings, who, dataset_id, doc_id)
    before = set(ids_in_index(ingress, who, dataset_id, doc_id))
    fake.embed_mode = "refuse"
    wait_run(ingress, who, dataset_id, doc_id, "4", timeout=180)
    fake.delay_ms, fake.embed_mode = 0, "ok"
    assert before, "no chunk was indexed before the provider refused"
    return before


# ----------------------------------------------------------------------------- cancel


def test_cancel_keeps_the_indexed_chunks_stops_within_five_seconds_and_parse_again_finishes(
    ingress: httpx.Client, owner: Account, fake: FakeProvider, settings: Settings, executors: list[str]
) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(CHUNKS))
    fake.delay_ms = 300
    assert start_parse(ingress, owner, dataset_id, [doc["id"]]).status_code == 200
    seconds = cancel_midway(ingress, owner, fake, settings, dataset_id, doc["id"])
    assert seconds <= 5, f"the row took {seconds:.1f} s to say run 2"

    kept = count_of(settings, owner, dataset_id, doc["id"])
    assert 0 < kept < CHUNKS, "chunks indexed before the cancel stay, the rest are never made"
    row = wait_until(
        lambda: (lambda r: r if r["chunk_count"] == kept else None)(doc_row(ingress, owner, dataset_id, doc["id"])),
        timeout=30, interval=1.0, describe=lambda: "the document total never equalled the index",
    )  # fmt: skip
    assert row["run"] == "2" and row["chunk_count"] > 0, "the SPA draws Partly indexed from run 2 with chunks"
    entry = wait_until(
        lambda: (lambda e: e if e["result"] == "cancelled" else None)(latest_log(ingress, owner, dataset_id, doc["id"])),
        timeout=30, interval=1.0, describe=lambda: "the log entry never closed as cancelled",
    )  # fmt: skip
    assert entry["chunk_count"] == kept
    stays(lambda: count_of(settings, owner, dataset_id, doc["id"]), kept)

    finish(ingress, owner, settings, dataset_id, doc["id"])


# ----------------------------------------------------------------------------- partial failure and the edited-chunk guard


def test_partial_failure_keeps_the_chunks_and_parse_again_replaces_them(
    ingress: httpx.Client, owner: Account, fake: FakeProvider, settings: Settings, executors: list[str]
) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(CHUNKS))
    before = fail_midway(ingress, owner, fake, settings, dataset_id, doc["id"])

    row = doc_row(ingress, owner, dataset_id, doc["id"])
    assert row["run"] == "4"
    after = set(ids_in_index(ingress, owner, dataset_id, doc["id"]))
    assert before <= after and 0 < len(after) < CHUNKS, "the chunks indexed before the refusal are still searchable"
    wait_until(
        lambda: doc_row(ingress, owner, dataset_id, doc["id"])["chunk_count"] == len(after),
        timeout=30, interval=1.0, describe=lambda: "the document total never equalled the index",
    )  # fmt: skip
    for chunk_id in sorted(before)[:3]:
        assert int(stored(settings, owner, where_of(dataset_id, doc["id"]), chunk_id)["available_int"]) == 1
    entry = latest_log(ingress, owner, dataset_id, doc["id"])
    assert entry["result"] == "failed"
    detail = ok(api(ingress, "GET", logs_path(dataset_id, entry["id"]), owner.token))
    assert detail["error"]["code"] == "provider_refused" and detail["retried"] is False

    finish(ingress, owner, settings, dataset_id, doc["id"])
    assert len(ids_in_index(ingress, owner, dataset_id, doc["id"])) == CHUNKS


def test_edited_chunk_after_a_failure_needs_a_confirmation_and_is_replaced(
    ingress: httpx.Client, owner: Account, fake: FakeProvider, settings: Settings, executors: list[str]
) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(CHUNKS))
    before = fail_midway(ingress, owner, fake, settings, dataset_id, doc["id"])
    target = sorted(before)[0]
    edited = patch_chunk(ingress, owner, where_of(dataset_id, doc["id"]), target, {"content_with_weight": "edited text about margins zzedited"})
    assert edited.status_code == 200, edited.text

    resp = start_parse(ingress, owner, dataset_id, [doc["id"]])
    assert resp.status_code == 409 and (resp.json()["data"] or {}).get("reason") == "confirm_required", resp.text
    assert resp.json()["data"]["documents"][0]["edited_count"] == 1

    finish(ingress, owner, settings, dataset_id, doc["id"], confirm=True)
    texts = [c["text"] for c in chunk_texts(api, ingress, owner.token, dataset_id, doc["id"])]
    assert not [t for t in texts if "zzedited" in t], "the edit is gone"


# ----------------------------------------------------------------------------- re-parse identity


def test_reparse_leaves_the_same_count_and_ids_also_after_a_cancel_and_after_a_failed_run(
    ingress: httpx.Client, owner: Account, fake: FakeProvider, settings: Settings, executors: list[str]
) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(CHUNKS))
    finish(ingress, owner, settings, dataset_id, doc["id"])
    first = sorted(ids_in_index(ingress, owner, dataset_id, doc["id"]))

    finish(ingress, owner, settings, dataset_id, doc["id"], confirm=True)
    assert sorted(ids_in_index(ingress, owner, dataset_id, doc["id"])) == first, "a confirmed re-parse"

    fake.delay_ms = 300
    assert start_parse(ingress, owner, dataset_id, [doc["id"]], confirm=True).status_code == 200
    cancel_midway(ingress, owner, fake, settings, dataset_id, doc["id"])
    finish(ingress, owner, settings, dataset_id, doc["id"])
    assert sorted(ids_in_index(ingress, owner, dataset_id, doc["id"])) == first, "after a cancelled run"

    fail_midway(ingress, owner, fake, settings, dataset_id, doc["id"], confirm=True)
    finish(ingress, owner, settings, dataset_id, doc["id"])
    assert sorted(ids_in_index(ingress, owner, dataset_id, doc["id"])) == first, "after a failed run"


# ----------------------------------------------------------------------------- delete during a running parse


def test_delete_a_document_during_a_parse_leaves_nothing_in_the_index(
    ingress: httpx.Client, owner: Account, fake: FakeProvider, settings: Settings, executors: list[str]
) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(CHUNKS))
    began = time.time()
    fake.delay_ms = 300
    assert start_parse(ingress, owner, dataset_id, [doc["id"]]).status_code == 200
    midway(settings, owner, dataset_id, doc["id"])
    resp = delete_docs(ingress, owner, dataset_id, [doc["id"]])
    assert resp.status_code == 200, resp.text
    wait_until(lambda: count_of(settings, owner, dataset_id, doc["id"]) == 0, timeout=60, interval=0.5, describe=lambda: "chunks remain after the delete")
    stays(lambda: count_of(settings, owner, dataset_id, doc["id"]), 0)
    fake.delay_ms = 0
    for cid in ctl.container_ids():
        assert "Traceback" not in ctl.logs_since(cid, began), f"traceback in the executor log of {cid[:12]}"
