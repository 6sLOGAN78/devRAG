"""Ingestion summary, parsing log, log detail, task status and the embedding-model check against the real MySQL and the loopback provider (plan 04-19).

KB-14, KB-15, KB-16, KB-19, DOC-22, DOC-23, D-07, D-08, D-23. Log rows come from the real roll-up wherever the outcome is one the worker produces;
the loopback provider is the other end of the wire. Waiting never uses a sleep.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from typing import Any

import pytest

from api.db.database import DB
from api.db.models import PipelineOperationLog
from api.db.services import ingestion_read_service as ir
from api.db.services import knowledgebase_service as kbsvc
from api.db.services.auth_service import AUTH_API, Principal
from api.db.services.service_errors import Kind, ServiceError
from api.db.services.tenant_scope import ActingScope
from common.ingest_codes import PLAIN_MESSAGES
from rag.svr.failure import format_failure_line
from rag.svr.progress import rollup_once
from test.helpers.accounts import AccountRegistry
from test.helpers.fake_provider import FakeProvider, running_fake_provider
from test.helpers.ingest import World, add_document, add_task, begin_run, cleanup_tasks, make_pipeline_world, poison_docx, put_chunks, set_task
from test.helpers.uploads import sql
from test.integration.test_chunk_service import add_document_to
from test.integration.test_document_service import team_dataset_of
from test.integration.test_knowledgebase_service import join, principal_of
from test.integration.test_upload_service import _bound_database  # noqa: F401  (autouse module fixture)
from test.testcases.conftest import BASE_URL

pytestmark = pytest.mark.integration

EMBEDDINGS = "/v1/embeddings"
DIM16 = "fake-dim16@OpenAI-API-Compatible"
KEY_SHAPE = "sk-" + "abcdefghijklmnopqrstuvwx0123456789"


@pytest.fixture
def registry() -> Iterator[AccountRegistry]:
    accounts = AccountRegistry(BASE_URL)
    try:
        yield accounts
    finally:
        cleanup_tasks(accounts)
        accounts.cleanup()


@pytest.fixture
def fake() -> Iterator[FakeProvider]:
    with running_fake_provider() as provider:
        yield provider


@pytest.fixture
def world(registry, fake) -> World:
    return make_pipeline_world(registry, fake)


# ----------------------------------------------------------------------------- helpers


def visible_of(world: World, who=None, dataset=None):
    return kbsvc.load_visible_dataset(principal_of(who or world.owner), (dataset or world.dataset).id)


def refused(call) -> ServiceError:
    with pytest.raises(ServiceError) as err:
        call()
    return err.value


def set_doc(doc_id: str, **values: Any) -> None:
    columns = ", ".join(f"`{key}` = %s" for key in values)
    sql(f"UPDATE `document` SET {columns} WHERE `id` = %s", (*values.values(), doc_id))  # noqa: S608  (column names come from the test)


def doc_in(world: World, name: str, *, run: str, chunks: int = 0, dataset=None) -> str:
    doc_id = add_document(world, name, f"{name} body".encode())
    set_doc(doc_id, run=run, chunk_num=chunks, token_num=chunks * 10)
    return doc_id


def log_row(world: World, doc_id: str, *, status: str, dsl: dict | None = None, msg: str = "", create_time: int | None = None, duration: float = 0.0) -> str:
    name, suffix, kind = sql("SELECT `name`, `suffix`, `type` FROM `document` WHERE `id` = %s", (doc_id,))[0]
    log_id = uuid.uuid4().hex
    extra = {} if create_time is None else {"create_time": create_time}
    with DB.connection_context():
        PipelineOperationLog.create(
            id=log_id, document_id=doc_id, tenant_id=world.owner.tenant_id, kb_id=world.dataset.id, parser_id="naive", document_name=name,
            document_suffix=suffix, document_type=kind, source_from="local", operation_status=status, dsl=dsl or {}, progress_msg=msg,
            process_duration=duration, task_type="parse", **extra,
        )  # fmt: skip
    return log_id


def running_doc(world: World, name: str = "a.txt") -> tuple[str, str]:
    doc = add_document(world, name, poison_docx() if name.endswith(".docx") else b"hello world")
    task = add_task(doc)
    begin_run(doc)
    return doc, task


def finish_through_rollup(world: World, doc: str) -> None:
    stats = rollup_once(world.settings, doc_ids=[doc])
    assert stats.finished + stats.failed == 1, stats


def only_log(world: World, doc_id: str) -> dict[str, Any]:
    items = ir.list_logs(visible_of(world), page=1, size=100)["items"]
    return next(item for item in items if item["document_id"] == doc_id)


# ----------------------------------------------------------------------------- summary


def test_the_summary_counts_every_state_and_partial_documents_from_one_grouped_statement(world):
    for i in range(2):
        doc_in(world, f"never{i}.txt", run="0")
    doc_in(world, "going.txt", run="1")
    for i in range(3):
        doc_in(world, f"done{i}.txt", run="3", chunks=4)
    doc_in(world, "failed-with.txt", run="4", chunks=4)
    doc_in(world, "failed-without.txt", run="4")
    doc_in(world, "cancelled.txt", run="2", chunks=3)
    sql("UPDATE `knowledgebase` SET `chunk_num` = 19, `token_num` = 190 WHERE `id` = %s", (world.dataset.id,))
    summary = ir.ingestion_summary(visible_of(world))
    assert summary == {"unstart": 2, "running": 1, "done": 3, "failed": 2, "cancelled": 1, "partial": 2, "chunk_total": 19, "token_total": 190}


def test_the_summary_of_an_empty_dataset_is_all_zero(world):
    assert ir.ingestion_summary(visible_of(world)) == {"unstart": 0, "running": 0, "done": 0, "failed": 0, "cancelled": 0, "partial": 0, "chunk_total": 0, "token_total": 0}


def test_the_summary_costs_at_most_two_statements(world, monkeypatch):
    for i in range(4):
        doc_in(world, f"d{i}.txt", run=str(i % 5), chunks=i)
    visible = visible_of(world)
    seen: list[str] = []
    real = DB.obj.execute_sql

    def counting(sql_text, params=None, *a, **k):
        seen.append(sql_text)
        return real(sql_text, params, *a, **k)

    monkeypatch.setattr(DB.obj, "execute_sql", counting)
    ir.ingestion_summary(visible)
    assert len(seen) <= 2, seen


# ----------------------------------------------------------------------------- log list


def test_the_log_is_newest_first_paged_and_shows_only_this_datasets_runs(world):
    other = team_dataset_of(world.settings, world.owner, world.owner)
    doc = doc_in(world, "a.txt", run="3", chunks=2)
    ids = [log_row(world, doc, status="done", dsl={"chunks": 2}, create_time=1_000 + i) for i in range(5)]
    other_doc = add_document_to(world, other)
    with DB.connection_context():
        PipelineOperationLog.create(
            id=uuid.uuid4().hex, document_id=other_doc, tenant_id=world.owner.tenant_id, kb_id=other.id, parser_id="naive", document_name="x.txt", document_suffix="txt",
            document_type="doc", source_from="local", operation_status="done", dsl={}, task_type="parse",
        )  # fmt: skip
    first = ir.list_logs(visible_of(world), page=1, size=2)
    assert first["total"] == 5
    assert [i["id"] for i in first["items"]] == list(reversed(ids))[:2]
    last = ir.list_logs(visible_of(world), page=3, size=2)
    assert [i["id"] for i in last["items"]] == [ids[0]]
    assert len(ir.list_logs(visible_of(world))["items"]) == 5, "the default page holds twenty"
    for bad in (0, 101, True, "2"):
        assert refused(lambda b=bad: ir.list_logs(visible_of(world), page=1, size=b)).kind is Kind.INVALID
    assert refused(lambda: ir.list_logs(visible_of(world), page=0, size=20)).kind is Kind.INVALID


def test_a_finished_run_reports_its_counts_from_the_real_rollup(world):
    doc, task = running_doc(world)
    set_task(task, 1.0, "10:00:01  done\n10:00:01  [pages] total=7 without_text=2", retry_count=1)
    put_chunks(world, doc, 5)
    finish_through_rollup(world, doc)
    entry = only_log(world, doc)
    assert set(entry) == set(ir.LOG_KEYS)
    assert (entry["result"], entry["chunk_count"], entry["pages_total"], entry["pages_without_text"], entry["attempts"]) == ("done", 5, 7, 2, 1)
    assert entry["max_attempts"] == world.settings.ingest.max_attempts and entry["retried"] is False and entry["error"] is None
    assert isinstance(entry["duration_seconds"], float) and round(entry["duration_seconds"], 1) == entry["duration_seconds"]
    assert entry["document_name"] == "a.txt" and entry["document_id"] == doc


def test_a_failed_run_that_used_its_attempts_is_retried_and_one_that_failed_at_once_is_not(world):
    doc, task = running_doc(world, "damaged.docx")
    line = format_failure_line("parse", "file_damaged", PLAIN_MESSAGES["file_damaged"])
    set_task(task, -1.0, f"10:00:01  trying\n10:00:02  {line}", retry_count=world.settings.ingest.max_attempts)
    finish_through_rollup(world, doc)
    entry = only_log(world, doc)
    assert entry["result"] == "failed" and entry["retried"] is True and entry["attempts"] == world.settings.ingest.max_attempts
    assert entry["error"] == {"step": "parse", "code": "file_damaged", "message": PLAIN_MESSAGES["file_damaged"]}

    quick, quick_task = running_doc(world, "empty.txt")
    set_task(quick_task, 1.0, "10:00:01  done", retry_count=1)
    finish_through_rollup(world, quick)  # no chunks in the index: no_readable_text, terminal at once
    again = only_log(world, quick)
    assert again["result"] == "failed" and again["retried"] is False and again["error"]["code"] == "no_readable_text"


def test_a_running_entry_shows_the_documents_current_chunk_count_and_no_error(world):
    doc = doc_in(world, "live.txt", run="1", chunks=9)
    log_row(world, doc, status="running", dsl={"tasks": 1})
    entry = only_log(world, doc)
    assert entry["result"] == "running" and entry["chunk_count"] == 9 and entry["error"] is None


def test_a_cancelled_entry_keeps_its_chunk_count_and_has_no_error(world):
    doc = doc_in(world, "stop.txt", run="2", chunks=3)
    log_row(world, doc, status="cancelled", dsl={"chunks": 3}, duration=4.26)
    entry = only_log(world, doc)
    assert (entry["result"], entry["chunk_count"], entry["error"], entry["duration_seconds"]) == ("cancelled", 3, None, 4.3)


# ----------------------------------------------------------------------------- log detail


def test_the_log_text_is_capped_redacted_and_free_of_traces_and_paths(world):
    doc = doc_in(world, "noisy.txt", run="3", chunks=1)
    lines = [f"10:00:00  line {i}" for i in range(3500)]
    lines[-1] = "10:00:09  Traceback (most recent call last):"
    lines[-2] = '10:00:09  File "/ragflow/rag/svr/x.py", line 3'
    lines[-3] = "10:00:09  read /tmp/work/a.bin and /ragflow/data/b via http://127.0.0.1:9000/bucket/key"
    lines[-4] = f"10:00:09  using {KEY_SHAPE} now"
    log_id = log_row(world, doc, status="done", dsl={"chunks": 1}, msg="\n".join(lines))
    detail = ir.get_log(visible_of(world), log_id)
    assert len(detail["log"]) <= 3000
    text = "\n".join(detail["log"])
    for banned in ("Traceback", "/ragflow", "/tmp", "127.0.0.1", KEY_SHAPE, 'File "'):
        assert banned not in text, banned
    assert detail["log"][0].endswith("line 500") or len(detail["log"]) == 3000


def test_a_log_of_another_dataset_or_a_bad_id_is_not_found(world):
    other = team_dataset_of(world.settings, world.owner, world.owner)
    other_doc = add_document_to(world, other)
    foreign = uuid.uuid4().hex
    with DB.connection_context():
        PipelineOperationLog.create(
            id=foreign, document_id=other_doc, tenant_id=world.owner.tenant_id, kb_id=other.id, parser_id="naive", document_name="x.txt", document_suffix="txt",
            document_type="doc", source_from="local", operation_status="done", dsl={}, task_type="parse",
        )  # fmt: skip
    for bad in (foreign, "nope", "", "../x", uuid.uuid4().hex, None):
        assert refused(lambda b=bad: ir.get_log(visible_of(world), b)).kind is Kind.NOT_FOUND, bad
    assert ir.get_log(visible_of(world, dataset=other), foreign)["id"] == foreign


def test_error_detail_appears_only_for_provider_refused_and_is_scrubbed_and_short(world):
    refused_doc = doc_in(world, "r.txt", run="4")
    long_text = "The request was refused for a reason. " * 30 + KEY_SHAPE + " see /srv/secret/path http://10.0.0.5:8080/x"
    dsl = {"error": {"step": "embed", "code": "provider_refused", "message": "free text must not be copied", "detail": long_text}, "attempts": 1}
    one = ir.get_log(visible_of(world), log_row(world, refused_doc, status="failed", dsl=dsl))
    detail = one["error"]["detail"]
    assert len(detail) <= 300 and KEY_SHAPE not in detail and "/srv" not in detail and "10.0.0.5" not in detail
    assert one["error"]["message"] == PLAIN_MESSAGES["provider_refused"] and one["error"]["step"] == "embed"

    other_doc = doc_in(world, "t.txt", run="4")
    dsl = {"error": {"step": "embed", "code": "provider_timeout", "message": "boom at /srv/x", "detail": "secret detail"}, "attempts": 3}
    two = ir.get_log(visible_of(world), log_row(world, other_doc, status="failed", dsl=dsl))
    assert "detail" not in two["error"] and two["error"]["message"] == PLAIN_MESSAGES["provider_timeout"]
    assert "boom" not in json.dumps(two)


def test_a_failed_entry_without_an_error_record_is_unexpected(world):
    doc = doc_in(world, "bare.txt", run="4")
    entry = ir.get_log(visible_of(world), log_row(world, doc, status="failed", dsl={}))
    assert entry["error"] == {"step": "parse", "code": "unexpected", "message": PLAIN_MESSAGES["unexpected"]}
    weird = ir.get_log(visible_of(world), log_row(world, doc, status="failed", dsl={"error": {"step": "x", "code": "made_up", "message": "m"}}))
    assert weird["error"]["code"] == "unexpected" and weird["error"]["step"] == "parse"


# ----------------------------------------------------------------------------- task status


def test_task_status_of_a_finished_a_failed_and_a_running_task(world):
    doc, task = running_doc(world)
    set_task(task, 1.0, "10:00:01  done\n10:00:02  Indexed 3 of 3 chunks.", retry_count=1)
    done = ir.task_status(principal_of(world.owner), task)
    assert done["finished"] is True and done["failed"] is False and done["error"] is None and done["attempts"] == 1
    assert done["progress_message"] == "Indexed 3 of 3 chunks." or done["progress_message"].endswith("Indexed 3 of 3 chunks.")
    assert (done["id"], done["doc_id"], done["dataset_id"]) == (task, doc, world.dataset.id)
    assert set(done) == set(ir.TASK_KEYS)

    bad_doc, bad = running_doc(world, "bad.docx")
    set_task(bad, -1.0, f"10:00:01  {format_failure_line('parse', 'file_damaged', PLAIN_MESSAGES['file_damaged'])}", retry_count=3)
    failed = ir.task_status(principal_of(world.owner), bad)
    assert failed["failed"] is True and failed["finished"] is False
    assert failed["error"] == {"step": "parse", "code": "file_damaged", "message": PLAIN_MESSAGES["file_damaged"]}

    live_doc, live = running_doc(world, "live.txt")
    set_task(live, 0.4, "10:00:01  Embedding")
    running = ir.task_status(principal_of(world.owner), live)
    assert running["finished"] is False and running["failed"] is False and running["error"] is None


def test_task_status_hides_private_datasets_other_tenants_and_absent_ids(world, registry):
    member, outsider = registry.register(prefix="tsm"), registry.register(prefix="tso")
    join(world.owner, member)
    scope = ActingScope(tenant_id=world.owner.tenant_id, role="owner", subject="owner")
    private = kbsvc.create_dataset(world.settings, scope, world.owner.user_id, kbsvc.CreateRequest(name=f"priv-{uuid.uuid4().hex[:6]}", permission="me"))
    doc = add_document_to(world, private)
    task = add_task(doc)
    assert ir.task_status(principal_of(world.owner), task)["dataset_id"] == private.id
    for who in (member, outsider):
        assert refused(lambda w=who: ir.task_status(principal_of(w), task)).kind is Kind.NOT_FOUND
    for bad in (uuid.uuid4().hex, "nope", "", None):
        assert refused(lambda b=bad: ir.task_status(principal_of(world.owner), b)).kind is Kind.NOT_FOUND


# ----------------------------------------------------------------------------- embedding check


def test_the_check_embeds_one_probe_with_the_datasets_model_and_reports_equal_sizes(world, fake):
    before = len(fake.hits(EMBEDDINGS))
    result = ir.embedding_check(world.embed_settings, visible_of(world), principal_of(world.owner), None)
    assert result == {"ok": True, "dimension": 8, "expected": 8}
    assert len(fake.hits(EMBEDDINGS)) == before + 1
    assert fake.hits(EMBEDDINGS)[-1].body["input"] in ([ir.PROBE_TEXT], ir.PROBE_TEXT)


def test_a_candidate_model_with_another_vector_size_is_reported_not_raised(world):
    result = ir.embedding_check(world.embed_settings, visible_of(world), principal_of(world.owner), DIM16)
    assert result == {"ok": False, "dimension": 16, "expected": 8}


def test_a_refused_provider_call_is_the_typed_reason_and_a_dead_one_is_not_an_auth_failure(world, fake):
    fake.embed_mode = "refuse"
    err = refused(lambda: ir.embedding_check(world.embed_settings, visible_of(world), principal_of(world.owner), None))
    assert err.reason == "provider_refused" and err.kind is Kind.INVALID
    fake.embed_mode = "ratelimit"
    err = refused(lambda: ir.embedding_check(world.embed_settings, visible_of(world), principal_of(world.owner), None))
    assert err.reason == "provider_rate_limited"


def test_only_a_manager_may_run_the_check_and_it_costs_nothing_when_refused(world, registry, fake):
    member = registry.register(prefix="chk")
    join(world.owner, member)
    team = team_dataset_of(world.settings, world.owner, world.owner)
    before = len(fake.hits(EMBEDDINGS))
    err = refused(lambda: ir.embedding_check(world.embed_settings, visible_of(world, member, team), principal_of(member), None))
    assert err.kind is Kind.FORBIDDEN
    token = Principal(world.owner.user_id, world.owner.tenant_id, "owner", AUTH_API, False)
    assert ir.authorize_check(token, world.dataset.id).dataset.id == world.dataset.id
    assert refused(lambda: ir.authorize_check(principal_of(member), team.id)).kind is Kind.FORBIDDEN
    assert len(fake.hits(EMBEDDINGS)) == before


def test_a_model_that_is_not_in_the_workspace_is_model_unavailable(world, fake):
    before = len(fake.hits(EMBEDDINGS))
    for bad in ("missing-model@OpenAI-API-Compatible", "not a ref", "x" * 200):
        err = refused(lambda b=bad: ir.embedding_check(world.embed_settings, visible_of(world), principal_of(world.owner), b))
        assert err.reason == "model_unavailable", bad
    assert len(fake.hits(EMBEDDINGS)) == before
