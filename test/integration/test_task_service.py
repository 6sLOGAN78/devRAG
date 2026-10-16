"""Task rows, the attempt counter and progress writers against the real MySQL (plan 04-10, ING-01, ING-11, D-05)."""
from __future__ import annotations

import uuid

import pytest

from api.db.database import DB
from api.db.models import Task
from api.db.services import task_service as ts
from test.helpers.uploads import sql, text_bytes
from test.integration import test_upload_service as base
from test.integration.test_document_service import team_dataset_of  # noqa: F401  (fixture helper parity)

pytestmark = pytest.mark.integration

_bound_database = base._bound_database
settings = base.settings
llm = base.llm
registry = base.registry
storage = base.storage
space = base.space
item = base.item
upload = base.upload


def make_task(doc_id: str, *, progress: float = 0.0, retry: int = 0) -> str:
    tid = uuid.uuid4().hex
    with DB.connection_context():
        Task.create(id=tid, doc_id=doc_id, from_page=0, to_page=1000000, task_type="parse", priority=0, digest="abc", progress=progress, retry_count=retry)
    return tid


def row_of(tid: str):
    with DB.connection_context():
        return Task.get_by_id(tid)


@pytest.fixture
def doc(settings, space, storage):
    owner, dataset = space
    made = upload(settings, owner, dataset, [item("t.txt", text_bytes("task"))], storage=storage)[0]
    yield made, owner, dataset
    sql("DELETE FROM `task` WHERE `doc_id` = %s", (made["id"],))


def test_claim_counts_up_to_the_cap_then_reports_exhausted(doc):
    made = doc[0]
    tid = make_task(made["id"])
    assert ts.claim_attempt(tid, 3) == ts.Claim("claimed", 1)
    assert ts.claim_attempt(tid, 3) == ts.Claim("claimed", 2)
    assert ts.claim_attempt(tid, 3) == ts.Claim("claimed", 3)
    assert ts.claim_attempt(tid, 3).outcome == "exhausted"
    assert row_of(tid).retry_count == 3
    assert row_of(tid).begin_at is not None


def test_claim_on_finished_failed_and_missing(doc):
    made = doc[0]
    assert ts.claim_attempt(make_task(made["id"], progress=1.0), 3).outcome == "finished"
    assert ts.claim_attempt(make_task(made["id"], progress=-1.0), 3).outcome == "finished"
    assert ts.claim_attempt(uuid.uuid4().hex, 3).outcome == "gone"


def test_refund_never_goes_below_zero(doc):
    tid = make_task(doc[0]["id"])
    ts.claim_attempt(tid, 3)
    ts.refund_attempt(tid)
    assert row_of(tid).retry_count == 0
    ts.refund_attempt(tid)
    assert row_of(tid).retry_count == 0


def test_load_context_joins_task_document_and_dataset(doc):
    made, owner, dataset = doc
    tid = make_task(made["id"])
    ctx = ts.load_task_context(tid)
    assert ctx is not None
    assert (ctx.task_id, ctx.doc_id, ctx.dataset_id, ctx.tenant_id) == (tid, made["id"], dataset.id, owner.tenant_id)
    assert ctx.doc_name == "t.txt" and ctx.doc_suffix == "txt" and ctx.doc_run == "0"
    assert ctx.parser_id == dataset.parser_id and ctx.embd_id == dataset.embd_id
    assert (ctx.from_page, ctx.to_page) == (0, 1000000)
    assert ts.load_task_context(uuid.uuid4().hex) is None
    sql("DELETE FROM `document` WHERE `id` = %s", (made["id"],))
    assert ts.load_task_context(tid) is None


def test_progress_lines_are_redacted_clamped_and_bounded(doc):
    tid = make_task(doc[0]["id"])
    ts.set_progress(tid, 1.5, "fetched sk-abcdefghijklmnopqrstuvwxyz0123456789")
    got = row_of(tid)
    assert 0 <= got.progress < 1
    assert "abcdefghijklmnopqrstuvwxyz0123456789" not in got.progress_msg
    with DB.connection_context():
        Task.update(progress_msg="\n".join(f"old {i}" for i in range(3000))).where(Task.id == tid).execute()
    ts.set_progress(tid, 0.2, "newest")
    lines = row_of(tid).progress_msg.splitlines()
    assert len(lines) == 3000 and lines[-1].endswith("newest") and lines[0].endswith("old 1")


def test_done_and_failed_writers(doc):
    made = doc[0]
    done = make_task(made["id"])
    ts.mark_task_done(done, ["a" * 32, "b" * 32], 1.25)
    got = row_of(done)
    assert got.progress == 1 and got.chunk_ids == f"{'a' * 32} {'b' * 32}" and got.process_duration == pytest.approx(1.25)
    failed = make_task(made["id"])
    ts.mark_task_failed(failed, "file_damaged: cannot read")
    got = row_of(failed)
    assert got.progress == -1 and "file_damaged" in got.progress_msg
    assert ts.task_is_current(done) and not ts.task_is_current(uuid.uuid4().hex)
    assert {t.id for t in ts.tasks_of(made["id"])} >= {done, failed}
