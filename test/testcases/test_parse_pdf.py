"""PDF parsing end to end on the real stack: the 13-page split, blank pages, a PDF without text and a damaged file (plan 04-21).

ING-01, PARSE-02, DOC-20, IDX-07, D-05, D-14, D-16, E2E-05, success criterion 1. Nothing of devRag is replaced; the loopback provider is the third
party's end of the embedding wire. Waiting is polling with a deadline.
"""
from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import valkey

from common.ingest_codes import PLAIN_MESSAGES
from common.settings import Settings, load_settings
from test.helpers.accounts import Account, AccountRegistry
from test.helpers.fake_provider import FakeProvider, running_stack_fake_provider
from test.helpers.ingest import (
    chunk_texts,
    dataset_row,
    doc_row,
    garbage_bytes,
    index_count,
    start_parse,
    task_rows,
    text_pdf,
    thirteen_page_pdf,
    upload_text,
    wait_run,
)
from test.helpers.uploads import sql
from test.helpers.wait import wait_until
from test.testcases.conftest import BASE_URL
from test.testcases.test_dataset_flow import create, workspace
from test.testcases.test_provider_flow import api, ok

pytestmark = pytest.mark.e2e

PDF = "application/pdf"
NO_TEXT_SENTENCE = "This PDF has no readable text."


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
    return workspace(ingress, registry, fake, "pdfs")


@pytest.fixture(scope="module")
def settings() -> Settings:
    return load_settings()


def new_dataset(ingress: httpx.Client, who: Account) -> str:
    return ok(create(ingress, who))["id"]


def task_table(doc_id: str) -> list[dict[str, Any]]:
    rows = sql("SELECT `id`, `from_page`, `to_page`, `progress`, `retry_count`, `chunk_ids` FROM `task` WHERE `doc_id` = %s ORDER BY `from_page`", (doc_id,))
    return [{"id": r[0], "from": int(r[1]), "to": int(r[2]), "progress": float(r[3]), "retry": int(r[4]), "chunk_ids": str(r[5] or "").split()} for r in rows]


def pending_for(settings: Settings, task_ids: set[str]) -> list[str]:
    """Pending stream entries whose message names one of ``task_ids`` (the group's whole backlog is not ours to judge)."""
    rd = settings.redis
    client = valkey.Valkey(host=rd.host, port=rd.port, password=rd.password or None, db=rd.db, socket_timeout=3, socket_connect_timeout=3, decode_responses=True)
    stream, group = f"{settings.ingest.queue_prefix}.0.common", settings.ingest.consumer_group
    try:
        entries = client.xpending_range(stream, group, "-", "+", 1000)
        found = []
        for entry in entries:
            for _, fields in client.xrange(stream, entry["message_id"], entry["message_id"]):
                if any(t in str(fields) for t in task_ids):
                    found.append(entry["message_id"])
        return found
    finally:
        client.close()


@pytest.fixture(scope="module")
def thirteen(ingress: httpx.Client, owner: Account, settings: Settings) -> SimpleNamespace:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, thirteen_page_pdf(), "thirteen.pdf", mime=PDF)
    before_parse = task_rows(doc["id"])
    resp = start_parse(ingress, owner, dataset_id, [doc["id"]])
    assert resp.status_code == 200, resp.text
    seen: list[float] = []

    def finished() -> dict[str, Any] | None:
        row = doc_row(ingress, owner, dataset_id, doc["id"])
        seen.append(float(row["progress"]))
        return row if row["run"] == "3" else None

    row = wait_until(finished, timeout=120, interval=0.5, describe=lambda: "the 13-page PDF never finished")
    return SimpleNamespace(dataset_id=dataset_id, doc=doc, before_parse=before_parse, row=row, progress=seen)


# ----------------------------------------------------------------------------- the 13-page PDF


def test_a_13_page_pdf_is_split_into_two_tasks_with_exact_ranges(ingress: httpx.Client, owner: Account, settings: Settings, thirteen: SimpleNamespace) -> None:
    assert thirteen.before_parse == [], "an upload creates no task rows"
    tasks = task_table(thirteen.doc["id"])
    assert [(t["from"], t["to"]) for t in tasks] == [(0, 12), (12, 13)]
    assert all(t["progress"] == 1 for t in tasks)
    first, second = (set(t["chunk_ids"]) for t in tasks)
    assert first and second and first.isdisjoint(second)
    listed = {c["id"] for c in chunk_texts(api, ingress, owner.token, thirteen.dataset_id, thirteen.doc["id"])}
    assert first | second == listed, "the union of the task manifests is the index"
    assert len(listed) == index_count(settings, owner.tenant_id, thirteen.dataset_id, thirteen.doc["id"])
    assert all(i.startswith(f"{thirteen.doc['id']}_12") for i in second), "ids of the second task start at 12 * 1000"
    assert all(int(i.rsplit("_", 1)[1]) < 1000 for i in first)


def test_every_page_is_in_some_chunk_and_the_last_pages_boxes_lie_inside_it(ingress: httpx.Client, owner: Account, thirteen: SimpleNamespace) -> None:
    resp = api(
        ingress, "GET", f"/api/v1/datasets/{thirteen.dataset_id}/documents/{thirteen.doc['id']}/chunks", owner.token, params={"size": "100"}
    )
    data = ok(resp)
    chunks = data["items"]
    assert {p["page"] for c in chunks for p in c["positions"]} == set(range(1, 14))
    last = [c for c in chunks if any(p["page"] == 13 for p in c["positions"])]
    assert last and any("Page 13" in c["text"] for c in last)
    width, height = data["page_sizes"]["13"]
    for chunk in last:
        for box in (p for p in chunk["positions"] if p["page"] == 13):
            assert 0 <= box["x0"] < box["x1"] <= width and 0 <= box["top"] < box["bottom"] <= height, (box, width, height)


def test_the_log_thumbnail_totals_and_progress_of_the_13_page_run(ingress: httpx.Client, owner: Account, settings: Settings, thirteen: SimpleNamespace) -> None:
    row = doc_row(ingress, owner, thirteen.dataset_id, thirteen.doc["id"])
    assert row["pages_total"] == 13 and row["pages_without_text"] == 0
    assert row["thumbnail"].startswith("data:image/jpeg;base64,") and len(row["thumbnail"]) <= 20000
    count = index_count(settings, owner.tenant_id, thirteen.dataset_id, thirteen.doc["id"])
    stored = ok(api(ingress, "GET", f"/api/v1/datasets/{thirteen.dataset_id}/ingestions/{row['last_log_id']}", owner.token))
    assert stored["pages_total"] == 13 and stored["pages_without_text"] == 0 and stored["chunk_count"] == count
    dataset = dataset_row(ingress, owner, thirteen.dataset_id)
    assert dataset["chunk_num"] == count == row["chunk_count"] and dataset["token_num"] == row["token_num"] > 0
    assert thirteen.progress == sorted(thirteen.progress) and thirteen.progress[-1] == 1, thirteen.progress


def test_the_stream_holds_no_pending_entry_for_the_finished_tasks(settings: Settings, thirteen: SimpleNamespace) -> None:
    ids = {t["id"] for t in task_table(thirteen.doc["id"])}
    wait_until(lambda: pending_for(settings, ids) == [], timeout=30, interval=1.0, describe=lambda: "an entry for a finished task is still pending")


def test_a_confirmed_reparse_gives_the_same_count_and_the_same_ids(ingress: httpx.Client, owner: Account, settings: Settings, thirteen: SimpleNamespace) -> None:
    before = sorted(c["id"] for c in chunk_texts(api, ingress, owner.token, thirteen.dataset_id, thirteen.doc["id"]))
    resp = start_parse(ingress, owner, thirteen.dataset_id, [thirteen.doc["id"]], confirm=True)
    assert resp.status_code == 200, resp.text
    row = wait_run(ingress, owner, thirteen.dataset_id, thirteen.doc["id"], "3", timeout=120)
    after = sorted(c["id"] for c in chunk_texts(api, ingress, owner.token, thirteen.dataset_id, thirteen.doc["id"]))
    assert after == before and row["chunk_count"] == len(before) == index_count(settings, owner.tenant_id, thirteen.dataset_id, thirteen.doc["id"])
    assert [(t["from"], t["to"]) for t in task_table(thirteen.doc["id"])] == [(0, 12), (12, 13)]


# ----------------------------------------------------------------------------- blank pages, no text, damage


def test_blank_pages_are_counted_and_the_text_pages_are_chunked(ingress: httpx.Client, owner: Account) -> None:
    dataset_id = new_dataset(ingress, owner)
    pages = [[f"Text page {p} first line", f"Text page {p} second line"] if p in (1, 3, 5) else None for p in range(1, 6)]
    doc = upload_text(ingress, owner, dataset_id, text_pdf(pages), "partly-blank.pdf", mime=PDF)
    assert start_parse(ingress, owner, dataset_id, [doc["id"]]).status_code == 200
    row = wait_run(ingress, owner, dataset_id, doc["id"], "3", timeout=120)
    assert row["pages_total"] == 5 and row["pages_without_text"] == 2
    log = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset_id}/ingestions/{row['last_log_id']}", owner.token))
    assert log["pages_total"] == 5 and log["pages_without_text"] == 2
    chunks = chunk_texts(api, ingress, owner.token, dataset_id, doc["id"])
    assert {p["page"] for c in chunks for p in c["positions"]} == {1, 3, 5}


def test_a_pdf_without_any_text_fails_at_once_with_the_plain_sentence(ingress: httpx.Client, owner: Account, settings: Settings) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, text_pdf([None, None, None]), "scan.pdf", mime=PDF)
    assert start_parse(ingress, owner, dataset_id, [doc["id"]]).status_code == 200
    row = wait_run(ingress, owner, dataset_id, doc["id"], "4", timeout=60)
    assert row["error"]["code"] == "no_readable_text" and row["error"]["message"] == NO_TEXT_SENTENCE == PLAIN_MESSAGES["no_readable_text"], row["error"]
    tasks = task_table(doc["id"])
    assert len(tasks) == 1 and tasks[0]["retry"] == 1, "one attempt: a missing text layer is not retried"
    log = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset_id}/ingestions/{row['last_log_id']}", owner.token))
    assert log["error"]["code"] == "no_readable_text" and log["retried"] is False and log["attempts"] == 1, log
    for banned in ("Traceback", "/tmp", "/ragflow", 'File "'):  # noqa: S108 - forbidden leak text, not a filesystem path used by this test
        assert banned not in str(row) + str(log), banned
    assert index_count(settings, owner.tenant_id, dataset_id, doc["id"]) == 0
    wait_until(lambda: pending_for(settings, {tasks[0]["id"]}) == [], timeout=30, interval=1.0, describe=lambda: "the failed task is still pending in the stream")
    page = api(ingress, "GET", f"/api/v1/datasets/{dataset_id}/documents/{doc['id']}/pages/2/image", owner.token)
    assert page.status_code == 200 and page.headers["content-type"] == "image/jpeg", "the page image is still served"


def test_a_damaged_pdf_fails_with_file_damaged_after_three_attempts(ingress: httpx.Client, owner: Account, settings: Settings) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, b"%PDF-1.4\n" + garbage_bytes(), "broken.pdf", mime=PDF)
    assert start_parse(ingress, owner, dataset_id, [doc["id"]]).status_code == 200
    row = wait_run(ingress, owner, dataset_id, doc["id"], "4", timeout=90)
    assert row["error"]["code"] == "file_damaged" and row["error"]["message"] == PLAIN_MESSAGES["file_damaged"], row["error"]
    log = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset_id}/ingestions/{row['last_log_id']}", owner.token))
    assert (log["attempts"], log["max_attempts"], log["retried"]) == (3, 3, True), log
    for banned in ("Traceback", "/tmp", "/ragflow", 'File "'):  # noqa: S108 - forbidden leak text, not a filesystem path used by this test
        assert banned not in str(row) + str(log), banned
    ids = {t["id"] for t in task_table(doc["id"])}
    wait_until(lambda: pending_for(settings, ids) == [], timeout=30, interval=1.0, describe=lambda: "the failed task is still pending in the stream")
