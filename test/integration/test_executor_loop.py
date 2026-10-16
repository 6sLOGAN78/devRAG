"""The executor loop end to end: collect, lock, run, retry, fail, cancel, finish (plan 04-12; ING-04..08, ING-11, ING-12, DOC-12, D-05, D-06, D-14, D-25, R-156..158).

Executors and the roll-up daemon run in threads of this process against the stack's real MySQL, Valkey, Elasticsearch and MinIO and the loopback
embedding provider. Waiting is event based (``wait_until``); no test sleeps.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from api.db.services.service_errors import ServiceError
from rag.svr import healthcheck
from rag.svr.executor_loop import Outcome
from test.helpers.accounts import AccountRegistry
from test.helpers.executor_rig import rig_for
from test.helpers.fake_provider import FakeProvider, running_fake_provider
from test.helpers.ingest import (
    World,
    add_document,
    add_task,
    cleanup_tasks,
    doc_state,
    indexed,
    log_state,
    make_docx,
    make_pipeline_world,
    paragraphs,
    task_state,
    text_pdf,
    thirteen_page_pdf,
    truncated,
)
from test.helpers.uploads import sql
from test.helpers.wait import wait_until
from test.integration.test_upload_service import _bound_database  # noqa: F401  (autouse module fixture)
from test.testcases.conftest import BASE_URL

pytestmark = pytest.mark.integration


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


def tasks_of(doc_id: str) -> list[str]:
    return [r[0] for r in sql("SELECT `id` FROM `task` WHERE `doc_id` = %s ORDER BY `from_page`", (doc_id,))]


def finished(doc_id: str, run: str = "3"):
    return lambda: doc_state(doc_id)["run"] == run


def test_a_text_document_is_parsed_indexed_and_finished(world):
    doc = add_document(world, "forty.txt", paragraphs(40))
    with rig_for(world) as rig:
        rig.start_rollup()
        rig.start_executor()
        rig.parse(doc)
        wait_until(finished(doc), timeout=60, interval=0.25, describe=lambda: str(doc_state(doc)))
        state = doc_state(doc)
        count = len(indexed(world, doc_id=[doc]))
        assert state["progress"] == 1 and count == 40 and state["chunk_num"] == count
        assert log_state(doc)["status"] == "done"
        wait_until(rig.drained, timeout=10, interval=0.1)


def test_a_thirteen_page_pdf_is_two_tasks_and_one_finish(world):
    doc = add_document(world, "thirteen.pdf", thirteen_page_pdf())
    with rig_for(world) as rig:
        rig.start_rollup()
        rig.start_executor()
        rig.parse(doc)
        wait_until(finished(doc), timeout=90, interval=0.25, describe=lambda: str(doc_state(doc)))
        ids = tasks_of(doc)
        assert len(ids) == 2
        assert [task_state(t)["progress"] for t in ids] == [1.0, 1.0]
        assert log_state(doc)["dsl"]["pages_total"] == 13
        assert log_state(doc)["status"] == "done"


def test_a_damaged_file_uses_every_attempt_and_fails_without_calling_the_provider(world, fake):
    doc = add_document(world, "cut.docx", truncated(make_docx(paragraphs=["hello there"] * 20)))
    with rig_for(world, max_attempts=3, retry_backoff_max_seconds=1) as rig:
        rig.start_rollup()
        rig.start_executor()
        rig.parse(doc)
        wait_until(finished(doc, "4"), timeout=60, interval=0.25, describe=lambda: str(task_state(tasks_of(doc)[0])))
        (task,) = tasks_of(doc)
        state = task_state(task)
        assert state["retry_count"] == 3 and state["progress"] == -1
        log = log_state(doc)
        assert log["dsl"]["error"]["code"] == "file_damaged"
        assert log["dsl"]["attempts"] == 3 and log["dsl"]["retried"] is True
        for text in (state["progress_msg"], log["progress_msg"], doc_state(doc)["progress_msg"]):
            assert "Traceback" not in text and tempfile.gettempdir() not in text and "ingest-" not in text
        assert "Attempt 1 of 3 did not finish" in state["progress_msg"]
        assert fake.hits("/v1/embeddings") == []
        wait_until(rig.drained, timeout=10, interval=0.1)


def test_a_pdf_without_any_text_fails_with_no_readable_text_after_one_attempt(world):
    doc = add_document(world, "blank.pdf", text_pdf([None, None, None]))
    with rig_for(world) as rig:
        rig.start_rollup()
        rig.start_executor()
        rig.parse(doc)
        wait_until(finished(doc, "4"), timeout=60, interval=0.25)
        (task,) = tasks_of(doc)
        assert task_state(task)["retry_count"] == 1
        assert log_state(doc)["dsl"]["error"]["code"] == "no_readable_text"


def test_a_method_that_is_not_built_is_refused_by_the_service_and_fails_terminal_in_the_worker(world):
    refused = add_document(world, "a.txt", paragraphs(2))
    sql("UPDATE `document` SET `parser_id` = 'qa' WHERE `id` = %s", (refused,))
    late = add_document(world, "b.txt", paragraphs(2))
    with rig_for(world) as rig:
        with pytest.raises(ServiceError):
            rig.parse(refused)
        rig.parse(late)
        sql("UPDATE `document` SET `parser_id` = 'qa' WHERE `id` = %s", (late,))
        rig.start_rollup()
        rig.start_executor()
        wait_until(finished(late, "4"), timeout=60, interval=0.25)
        (task,) = tasks_of(late)
        assert task_state(task)["retry_count"] == 1
        assert log_state(late)["dsl"]["error"]["code"] == "chunker_unavailable"
        assert log_state(late)["dsl"]["retried"] is False


def test_a_stale_digest_and_a_vanished_task_are_acknowledged_and_ignored(world):
    doc = add_document(world, "stale.txt", paragraphs(2))
    task = add_task(doc)
    with rig_for(world) as rig:
        rig.queue.enqueue(task, "not-the-digest")
        rig.queue.enqueue(uuid.uuid4().hex, "gone")
        rig.start_executor()
        wait_until(rig.drained, timeout=20, interval=0.1)
        assert task_state(task) == {"progress": 0.0, "retry_count": 0, "progress_msg": ""}
        assert indexed(world, doc_id=[doc]) == []


def test_cancel_keeps_the_document_cancelled_and_the_task_stops_within_three_seconds(world, fake):
    fake.delay_ms = 300
    doc = add_document(world, "cancel.txt", paragraphs(40))
    with rig_for(world, batch_size=8) as rig:
        rig.start_rollup()
        runner = rig.start_executor()
        rig.parse(doc)
        wait_until(lambda: len(indexed(world, doc_id=[doc])) > 0, timeout=60, interval=0.05)
        assert rig.cancel(doc) == [doc]
        wait_until(rig.drained, timeout=3, interval=0.05, describe=lambda: str(runner.executor.outcomes))
        assert runner.executor.outcomes[Outcome.CANCELLED] == 1
        history: list[int] = []

        def stable() -> bool:
            history.append(len(indexed(world, doc_id=[doc])))
            return len(history) >= 3 and len(set(history[-3:])) == 1

        wait_until(stable, timeout=20, interval=0.3)
        assert 0 < history[-1] < 40
        assert doc_state(doc)["run"] == "2"
        assert log_state(doc)["status"] == "cancelled"


def test_two_executors_share_the_work_without_duplicate_chunks(world):
    docs = [add_document(world, f"d{i}.txt", paragraphs(3)) for i in range(6)]
    with rig_for(world) as rig:
        rig.start_rollup()
        rig.start_executor()
        rig.start_executor()
        rig.parse(*docs)
        for doc in docs:
            wait_until(finished(doc), timeout=90, interval=0.25, describe=lambda doc=doc: str(doc_state(doc)))
        for doc in docs:
            assert [task_state(t)["retry_count"] for t in tasks_of(doc)] == [1]
        ids = [h["id"] for h in indexed(world, doc_id=docs)]
        assert len(ids) == 18 and len(set(ids)) == 18


def test_the_alive_file_is_fresh_after_a_touch_and_stale_or_missing_otherwise():
    path = Path(tempfile.mkdtemp(prefix="alive-")) / "alive"
    assert healthcheck.is_alive(path, 30) is False
    healthcheck.touch_alive(path)
    assert healthcheck.is_alive(path, 30) is True
    os.utime(path, (1, 1))
    assert healthcheck.is_alive(path, 30) is False


def test_an_executor_touches_the_alive_file_while_it_runs(world, monkeypatch, tmp_path):
    target = tmp_path / "alive"
    monkeypatch.setattr(healthcheck, "ALIVE_FILE", target)
    with rig_for(world) as rig:
        rig.start_executor()
        wait_until(lambda: healthcheck.is_alive(target, 30), timeout=15, interval=0.1)
