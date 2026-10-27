"""Ingestion summary, parsing log, log detail, task status and the embedding check end to end on the running stack (plan 04-19).

KB-14, KB-15, KB-16, KB-19, DOC-22, DOC-23, E2E-05, D-07, D-08, D-23. Nothing of devRag is replaced: Nginx, the app, the task executor, MySQL, MinIO,
Valkey and Elasticsearch are the running stack. The loopback provider is the third party's end of the embedding wire. One dataset holds a finished
text file, a damaged .docx that fails after its attempts, a cancelled document and two documents that were never parsed.
"""
from __future__ import annotations

import json
import re
import time
from collections.abc import Iterator
from types import SimpleNamespace

import httpx
import pytest

from common.ingest_codes import PLAIN_MESSAGES
from common.settings import Settings, load_settings
from test.helpers.accounts import Account, AccountRegistry
from test.helpers.fake_provider import FakeProvider, running_stack_fake_provider
from test.helpers.ingest import dataset_row, doc_row, index_count, paragraphs, poison_docx, start_parse, task_rows, upload_text, wait_run
from test.helpers.wait import wait_until
from test.testcases.conftest import BASE_URL
from test.testcases.test_dataset_flow import create, workspace
from test.testcases.test_provider_flow import NOT_FOUND, api, join, ok

pytestmark = pytest.mark.e2e

FORBIDDEN = {"code": 403, "message": "forbidden", "data": None}
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
LONG = 200
KEY_SHAPE = re.compile(r"sk-[A-Za-z0-9_-]{20,}")
SUMMARY_KEYS = {"unstart", "running", "done", "failed", "cancelled", "partial", "chunk_total", "token_total"}
LOG_KEYS = {
    "id", "document_id", "document_name", "started_at", "duration_seconds", "result", "attempts", "max_attempts", "retried", "chunk_count",
    "pages_total", "pages_without_text", "error",
}  # fmt: skip
TASK_KEYS = {"id", "doc_id", "dataset_id", "from_page", "to_page", "progress", "progress_message", "attempts", "finished", "failed", "error"}


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
    return workspace(ingress, registry, fake, "ingest")


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


def reason_of(resp: httpx.Response) -> object:
    return (resp.json().get("data") or {}).get("reason")


def summary_path(dataset_id: str) -> str:
    return f"/api/v1/datasets/{dataset_id}/ingestions/summary"


def logs_path(dataset_id: str, log_id: str | None = None) -> str:
    base = f"/api/v1/datasets/{dataset_id}/ingestions"
    return base if log_id is None else f"{base}/{log_id}"


def task_path(task_id: str) -> str:
    return f"/v1/task/status/{task_id}"


def check_path(dataset_id: str) -> str:
    return f"/api/v1/datasets/{dataset_id}/embedding/check"


def count_stable(settings: Settings, owner: Account, dataset_id: str, doc_id: str) -> int:
    state = {"count": -1, "since": time.monotonic()}

    def stable() -> bool:
        now_count = index_count(settings, owner.tenant_id, dataset_id, doc_id)
        if now_count != state["count"]:
            state.update(count=now_count, since=time.monotonic())
            return False
        return time.monotonic() - state["since"] >= 6

    wait_until(stable, timeout=90, interval=1.0, describe=lambda: "the count never settled")
    return state["count"]


@pytest.fixture(scope="module")
def journey(ingress: httpx.Client, owner: Account, fake: FakeProvider, settings: Settings) -> SimpleNamespace:
    dataset_id = ok(create(ingress, owner))["id"]
    good = upload_text(ingress, owner, dataset_id, paragraphs(3))
    assert start_parse(ingress, owner, dataset_id, [good["id"]]).status_code == 200
    wait_run(ingress, owner, dataset_id, good["id"], "3", timeout=120)

    stopped = upload_text(ingress, owner, dataset_id, paragraphs(LONG))
    fake.delay_ms = 2000
    try:
        assert start_parse(ingress, owner, dataset_id, [stopped["id"]]).status_code == 200
        wait_until(lambda: index_count(settings, owner.tenant_id, dataset_id, stopped["id"]) > 0, timeout=90, interval=1.0, describe=lambda: "no chunk was indexed")
        assert start_parse(ingress, owner, dataset_id, [stopped["id"]], run="2").status_code == 200
    finally:
        fake.delay_ms = 0
    count_stable(settings, owner, dataset_id, stopped["id"])

    bad = upload_text(ingress, owner, dataset_id, poison_docx(), "damaged.docx", mime=DOCX)
    assert start_parse(ingress, owner, dataset_id, [bad["id"]]).status_code == 200
    wait_run(ingress, owner, dataset_id, bad["id"], "4", timeout=180)
    wait_until(
        lambda: any(i["result"] == "failed" for i in ok(api(ingress, "GET", logs_path(dataset_id), owner.token))["items"]),
        timeout=60, interval=1.0, describe=lambda: "the failed run never reached the log",
    )  # fmt: skip

    idle = [upload_text(ingress, owner, dataset_id, paragraphs(1), f"idle{i}.txt") for i in range(2)]
    return SimpleNamespace(dataset_id=dataset_id, good=good["id"], stopped=stopped["id"], bad=bad["id"], idle=[d["id"] for d in idle])


# ----------------------------------------------------------------------------- summary


def test_the_summary_counts_are_exact_and_the_totals_are_the_datasets_counters(ingress: httpx.Client, owner: Account, journey: SimpleNamespace) -> None:
    data = ok(api(ingress, "GET", summary_path(journey.dataset_id), owner.token))
    assert set(data) == SUMMARY_KEYS
    dataset = dataset_row(ingress, owner, journey.dataset_id)
    assert (data["unstart"], data["running"], data["done"], data["failed"], data["cancelled"], data["partial"]) == (2, 0, 1, 1, 1, 1)
    assert data["chunk_total"] == dataset["chunk_num"] > 0 and data["token_total"] == dataset["token_num"]


# ----------------------------------------------------------------------------- the log


def test_the_log_lists_newest_first_with_results_and_never_a_status_key(ingress: httpx.Client, owner: Account, journey: SimpleNamespace) -> None:
    page = ok(api(ingress, "GET", logs_path(journey.dataset_id), owner.token))
    assert page["total"] == 3 and [i["result"] for i in page["items"]] == ["failed", "cancelled", "done"]
    assert all(set(i) == LOG_KEYS for i in page["items"])
    assert "status" not in json.dumps(page)
    small = ok(api(ingress, "GET", logs_path(journey.dataset_id), owner.token, params={"size": "1", "page": "2"}))
    assert small["total"] == 3 and [i["result"] for i in small["items"]] == ["cancelled"]
    for bad in ({"size": "101"}, {"size": "0"}, {"page": "0"}, {"size": "x"}):
        resp = api(ingress, "GET", logs_path(journey.dataset_id), owner.token, params=bad)
        assert resp.status_code == 400 and reason_of(resp) == "query_invalid", (bad, resp.text)


def test_a_damaged_document_fails_after_its_attempts_with_a_plain_error_and_no_internals(ingress: httpx.Client, owner: Account, journey: SimpleNamespace) -> None:
    items = ok(api(ingress, "GET", logs_path(journey.dataset_id), owner.token))["items"]
    failed = next(i for i in items if i["result"] == "failed")
    resp = api(ingress, "GET", logs_path(journey.dataset_id, failed["id"]), owner.token)
    entry = ok(resp)
    assert (entry["attempts"], entry["max_attempts"], entry["retried"]) == (3, 3, True)
    assert entry["document_id"] == journey.bad and entry["document_name"] == "damaged.docx"
    assert entry["error"] == {"step": "parse", "code": "file_damaged", "message": PLAIN_MESSAGES["file_damaged"]}
    assert len(entry["log"]) >= 1 and len(entry["log"]) <= 3000
    for banned in ("Traceback", "/ragflow", "/tmp", "127.0.0.1", "host.docker.internal", 'File "'):  # noqa: S108 - forbidden leak text, not a filesystem path used by this test
        assert banned not in resp.text, banned
    assert KEY_SHAPE.search(resp.text) is None


def test_a_finished_entry_reports_the_index_count_and_a_cancelled_one_keeps_its_chunks(ingress: httpx.Client, owner: Account, journey: SimpleNamespace, settings: Settings) -> None:
    items = ok(api(ingress, "GET", logs_path(journey.dataset_id), owner.token))["items"]
    done = next(i for i in items if i["result"] == "done")
    stopped = next(i for i in items if i["result"] == "cancelled")
    assert done["chunk_count"] == index_count(settings, owner.tenant_id, journey.dataset_id, journey.good) == 3
    assert done["error"] is None and stopped["error"] is None
    assert stopped["chunk_count"] == index_count(settings, owner.tenant_id, journey.dataset_id, journey.stopped) > 0
    assert doc_row(ingress, owner, journey.dataset_id, journey.stopped)["run"] == "2"


# ----------------------------------------------------------------------------- task status


def test_task_status_of_a_finished_and_of_a_poisoned_task(ingress: httpx.Client, owner: Account, journey: SimpleNamespace) -> None:
    (good_task,) = task_rows(journey.good)
    done = ok(api(ingress, "GET", task_path(good_task), owner.token))
    assert set(done) == TASK_KEYS and done["finished"] is True and done["failed"] is False and done["error"] is None
    assert (done["doc_id"], done["dataset_id"]) == (journey.good, journey.dataset_id)
    (bad_task,) = task_rows(journey.bad)
    failed = ok(api(ingress, "GET", task_path(bad_task), owner.token))
    assert failed["failed"] is True and failed["finished"] is False and failed["attempts"] == 3
    assert failed["error"] == {"step": "parse", "code": "file_damaged", "message": PLAIN_MESSAGES["file_damaged"]}


# ----------------------------------------------------------------------------- isolation


def test_another_tenant_and_absent_ids_get_the_one_404(ingress: httpx.Client, registry: AccountRegistry, owner: Account, journey: SimpleNamespace) -> None:
    stranger = registry.register(prefix="ingstr")
    log_id = ok(api(ingress, "GET", logs_path(journey.dataset_id), owner.token))["items"][0]["id"]
    (task_id,) = task_rows(journey.good)
    for path in (summary_path(journey.dataset_id), logs_path(journey.dataset_id), logs_path(journey.dataset_id, log_id), task_path(task_id)):
        resp = api(ingress, "GET", path, stranger.token)
        assert resp.status_code == 404 and resp.json() == NOT_FOUND, (path, resp.text)
    for path in (logs_path(journey.dataset_id, "0" * 32), logs_path(journey.dataset_id, "nope"), task_path("0" * 32), task_path("nope"), summary_path("0" * 32)):
        resp = api(ingress, "GET", path, owner.token)
        assert resp.status_code == 404 and resp.json() == NOT_FOUND, (path, resp.text)
    resp = api(ingress, "POST", check_path(journey.dataset_id), stranger.token, body={})
    assert resp.status_code == 404 and resp.json() == NOT_FOUND


def test_a_private_datasets_runs_and_task_are_not_found_for_another_member(ingress: httpx.Client, registry: AccountRegistry, owner: Account) -> None:
    member = registry.register(prefix="ingmem")
    join(ingress, owner, member)
    dataset_id = ok(create(ingress, owner, permission="me"))["id"]
    doc = upload_text(ingress, owner, dataset_id, paragraphs(1))
    assert start_parse(ingress, owner, dataset_id, [doc["id"]]).status_code == 200
    wait_run(ingress, owner, dataset_id, doc["id"], "3", timeout=120)
    wait_until(
        lambda: ok(api(ingress, "GET", logs_path(dataset_id), owner.token))["total"] == 1, timeout=30, interval=1.0, describe=lambda: "the run never reached the log"
    )
    log_id = ok(api(ingress, "GET", logs_path(dataset_id), owner.token))["items"][0]["id"]
    (task_id,) = task_rows(doc["id"])
    for path in (summary_path(dataset_id), logs_path(dataset_id), logs_path(dataset_id, log_id), task_path(task_id)):
        resp = api(ingress, "GET", path, member.token)
        assert resp.status_code == 404 and resp.json() == NOT_FOUND, (path, resp.text)
        assert api(ingress, "GET", path, owner.token).status_code == 200


def test_a_team_member_reads_the_runs_of_a_team_dataset(ingress: httpx.Client, registry: AccountRegistry, owner: Account, journey: SimpleNamespace) -> None:
    member = registry.register(prefix="ingrd")
    join(ingress, owner, member)
    shared = ok(create(ingress, owner, permission="team"))["id"]
    assert ok(api(ingress, "GET", summary_path(shared), member.token))["unstart"] == 0
    assert ok(api(ingress, "GET", logs_path(shared), member.token))["total"] == 0


# ----------------------------------------------------------------------------- embedding check


def test_the_owner_checks_the_datasets_model(ingress: httpx.Client, owner: Account, journey: SimpleNamespace) -> None:
    data = ok(api(ingress, "POST", check_path(journey.dataset_id), owner.token, body={}))
    assert data["ok"] is True and data["dimension"] == data["expected"] > 0
    assert set(data) == {"ok", "dimension", "expected"}


def test_a_non_manager_is_forbidden_and_a_bad_body_or_model_is_a_typed_error(ingress: httpx.Client, registry: AccountRegistry, owner: Account, journey: SimpleNamespace) -> None:
    member = registry.register(prefix="ingchk")
    join(ingress, owner, member)
    shared = ok(create(ingress, owner, permission="team"))["id"]
    resp = api(ingress, "POST", check_path(shared), member.token, body={})
    assert resp.status_code == 403 and resp.json() == FORBIDDEN, resp.text
    unknown = api(ingress, "POST", check_path(journey.dataset_id), owner.token, body={"embd_id": "missing-model@OpenAI-API-Compatible"})
    assert unknown.status_code in (404, 409) and reason_of(unknown) == "model_unavailable", unknown.text
    extra = api(ingress, "POST", check_path(journey.dataset_id), owner.token, body={"embd_id": None, "other": 1})
    assert extra.status_code == 400, extra.text


def test_a_refusing_provider_is_a_typed_400_and_never_a_401(ingress: httpx.Client, owner: Account, journey: SimpleNamespace, fake: FakeProvider) -> None:
    fake.embed_mode = "refuse"
    resp = api(ingress, "POST", check_path(journey.dataset_id), owner.token, body={})
    assert resp.status_code == 400 and reason_of(resp) == "provider_refused", resp.text
    assert resp.status_code != 401


def test_calls_without_a_credential_are_401(ingress: httpx.Client, journey: SimpleNamespace) -> None:
    ingress.cookies.clear()
    for method, path in (("GET", summary_path(journey.dataset_id)), ("GET", logs_path(journey.dataset_id)), ("POST", check_path(journey.dataset_id)), ("GET", task_path("0" * 32))):
        resp = ingress.request(method, path, json={} if method == "POST" else None)
        assert resp.status_code == 401, (path, resp.status_code)
