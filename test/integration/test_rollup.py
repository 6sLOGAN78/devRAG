"""Roll-up, reconciler and per-task watcher against the real MySQL, Valkey and Elasticsearch (plan 04-12; ING-08, ING-10, ING-12, DOC-12, D-06, D-14, R-157)."""

from __future__ import annotations

import dataclasses
import secrets
import threading
from collections.abc import Iterator

import pytest
import valkey

from api.db.services import task_service
from common.ingest_codes import PLAIN_MESSAGES
from common.settings import Settings
from rag.queue.valkey_streams import ValkeyStreamQueue
from rag.svr.control import TaskControl
from rag.svr.failure import format_failure_line
from rag.svr.heartbeat import TaskWatcher
from rag.svr.progress import RollUpDaemon, reconcile_once, rollup_once
from rag.svr.task_lock import TaskLock
from test.helpers.accounts import AccountRegistry
from test.helpers.fake_provider import FakeProvider, running_fake_provider
from test.helpers.ingest import (
    World,
    add_document,
    add_task,
    age_task,
    begin_run,
    cleanup_tasks,
    doc_state,
    indexed,
    log_state,
    make_pipeline_world,
    put_chunks,
    set_task,
)
from test.helpers.uploads import sql
from test.helpers.wait import wait_until
from test.integration.test_upload_service import _bound_database  # noqa: F401  (autouse module fixture)
from test.testcases.conftest import BASE_URL

pytestmark = pytest.mark.integration

PAGES = "[pages] total=7 without_text=2"
SKIPPED = "[skipped] images=3"


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


@pytest.fixture
def env() -> Iterator[tuple[Settings, ValkeyStreamQueue, valkey.Valkey]]:
    from common.settings import load_settings

    base = load_settings()
    prefix = f"ru{secrets.token_hex(6)}"
    ingest = dataclasses.replace(base.ingest, queue_prefix=prefix, consumer_group=f"g{secrets.token_hex(4)}", reconcile_after_seconds=60, lock_ttl_seconds=5)
    settings = dataclasses.replace(base, ingest=ingest)
    rd = settings.redis
    raw = valkey.Valkey(host=rd.host, port=rd.port, password=rd.password or None, db=rd.db, socket_timeout=3, socket_connect_timeout=3)
    queue = ValkeyStreamQueue(settings)
    yield settings, queue, raw
    for key in raw.scan_iter(match=prefix + "*"):
        raw.delete(key)
    assert list(raw.scan_iter(match=prefix + "*")) == []
    queue.close()
    raw.close()


def running_doc(world: World, name: str = "a.txt", tasks: int = 1) -> tuple[str, list[str]]:
    doc = add_document(world, name, b"hello world")
    ids = [add_task(doc, i * 12, (i + 1) * 12) for i in range(tasks)]
    begin_run(doc, tasks)
    return doc, ids


def roll(world: World, doc: str):
    return rollup_once(world.settings, doc_ids=[doc])


# ----------------------------------------------------------------------------- roll-up


def test_progress_is_the_mean_and_the_merged_lines_reach_the_log_row(world):
    doc, (a, b) = running_doc(world, tasks=2)
    set_task(a, 0.5, "10:00:01  Indexed 5 of 10 chunks.")
    set_task(b, 1.0, "10:00:02  Indexed 10 of 10 chunks.")
    roll(world, doc)
    state = doc_state(doc)
    assert state["run"] == "1"
    assert state["progress"] == pytest.approx(0.75)
    assert "Indexed 5 of 10 chunks." in state["progress_msg"] and "Indexed 10 of 10 chunks." in state["progress_msg"]
    log = log_state(doc)
    assert log["status"] == "running"
    assert log["progress_msg"] == state["progress_msg"]
    assert log["progress"] == pytest.approx(0.75)


def test_merged_message_keeps_at_most_3000_lines(world):
    doc, (a,) = running_doc(world)
    set_task(a, 0.2, "\n".join(f"10:00:00  line {i}" for i in range(3500)))
    roll(world, doc)
    assert len(doc_state(doc)["progress_msg"].splitlines()) == 3000


def test_every_task_done_with_chunks_finishes_the_document(world):
    doc, (a, b) = running_doc(world, tasks=2)
    set_task(a, 1.0, f"10:00:01  done\n10:00:01  {PAGES}\n10:00:01  {SKIPPED}", retry_count=1)
    set_task(b, 1.0, "10:00:02  done\n10:00:02  [pages] total=1 without_text=0\n10:00:02  [skipped] images=0", retry_count=2)
    put_chunks(world, doc, 5)
    stats = roll(world, doc)
    assert stats.finished == 1
    state = doc_state(doc)
    assert state["run"] == "3" and state["progress"] == 1
    assert state["process_duration"] > 0
    assert state["chunk_num"] == 5
    log = log_state(doc)
    assert log["status"] == "done"
    assert log["dsl"]["tasks"] == 2
    assert log["dsl"]["attempts"] == 2
    assert log["dsl"]["chunks"] == 5
    assert log["dsl"]["pages_total"] == 8
    assert log["dsl"]["pages_without_text"] == 2
    assert log["dsl"]["images_skipped"] == 3
    assert "[pages]" not in state["progress_msg"]
    assert {h["doc_enabled_int"] for h in indexed(world, doc_id=[doc])} == {1}


def test_the_latest_page_line_of_a_retried_task_wins(world):
    doc, (a,) = running_doc(world)
    set_task(a, 1.0, "10:00:01  [pages] total=9 without_text=9\n10:00:02  [pages] total=4 without_text=1", retry_count=2)
    put_chunks(world, doc, 1)
    roll(world, doc)
    dsl = log_state(doc)["dsl"]
    assert (dsl["pages_total"], dsl["pages_without_text"]) == (4, 1)


def test_the_document_switch_is_reapplied_to_every_chunk_on_completion(world):
    doc, (a,) = running_doc(world)
    set_task(a, 1.0, "10:00:01  done")
    put_chunks(world, doc, 3, enabled=True)
    sql("UPDATE `document` SET `status` = '0' WHERE `id` = %s", (doc,))
    roll(world, doc)
    assert doc_state(doc)["run"] == "3"
    assert {h["doc_enabled_int"] for h in indexed(world, doc_id=[doc])} == {0}


def test_every_task_done_with_no_chunk_fails_with_no_readable_text(world):
    doc, (a,) = running_doc(world)
    set_task(a, 1.0, "10:00:01  done", retry_count=1)
    roll(world, doc)
    state = doc_state(doc)
    assert state["run"] == "4" and state["progress"] == -1
    log = log_state(doc)
    assert log["status"] == "failed"
    assert log["dsl"]["error"] == {"step": "parse", "code": "no_readable_text", "message": PLAIN_MESSAGES["no_readable_text"]}
    assert log["dsl"]["retried"] is False


def test_a_failed_task_fails_the_document_at_once_and_keeps_the_indexed_chunks(world):
    doc, (a, b) = running_doc(world, tasks=2)
    line = format_failure_line("embed", "provider_timeout", PLAIN_MESSAGES["provider_timeout"])
    set_task(a, -1, f"10:00:01  {line}", retry_count=3)
    set_task(b, 0.3, "10:00:01  working", retry_count=1)
    put_chunks(world, doc, 4)
    roll(world, doc)
    state = doc_state(doc)
    assert state["run"] == "4" and state["progress"] == -1
    assert state["chunk_num"] == 4
    assert len(indexed(world, doc_id=[doc])) == 4
    log = log_state(doc)
    assert log["status"] == "failed"
    assert log["dsl"]["error"] == {"step": "embed", "code": "provider_timeout", "message": PLAIN_MESSAGES["provider_timeout"]}
    assert log["dsl"]["attempts"] == 3 and log["dsl"]["retried"] is True


def test_a_terminal_failure_is_not_reported_as_retried(world):
    doc, (a,) = running_doc(world)
    set_task(a, -1, "10:00:01  " + format_failure_line("embed", "dimension_mismatch", PLAIN_MESSAGES["dimension_mismatch"]), retry_count=1)
    roll(world, doc)
    log = log_state(doc)
    assert log["dsl"]["error"]["code"] == "dimension_mismatch"
    assert log["dsl"]["retried"] is False and log["dsl"]["attempts"] == 1


def test_a_cancelled_document_and_a_document_without_tasks_are_not_touched(world):
    cancelled, (a,) = running_doc(world, "c.txt")
    set_task(a, 1.0, "10:00:01  done")
    sql("UPDATE `document` SET `run` = '2' WHERE `id` = %s", (cancelled,))
    bare = add_document(world, "b.txt", b"x")
    sql("UPDATE `document` SET `run` = '1' WHERE `id` = %s", (bare,))
    rollup_once(world.settings, doc_ids=[cancelled, bare])
    assert doc_state(cancelled)["run"] == "2"
    assert doc_state(bare)["run"] == "1"


def test_a_cancel_that_lands_during_the_cycle_wins(world, monkeypatch):
    doc, (a,) = running_doc(world)
    set_task(a, 1.0, "10:00:01  done")
    put_chunks(world, doc, 2)
    from rag.svr import progress

    real = progress.settle_totals

    def cancelling(*args, **kwargs):
        sql("UPDATE `document` SET `run` = '2' WHERE `id` = %s", (doc,))
        return real(*args, **kwargs)

    monkeypatch.setattr(progress, "settle_totals", cancelling)
    roll(world, doc)
    assert doc_state(doc)["run"] == "2"
    assert log_state(doc)["status"] == "running"


def test_only_the_holder_of_the_progress_lock_runs_a_cycle(world, env):
    settings, queue, raw = env
    doc, (a,) = running_doc(world)
    set_task(a, 0.5, "10:00:01  half")
    cfg = dataclasses.replace(world.settings, ingest=settings.ingest)
    daemon = RollUpDaemon(cfg, queue, threading.Event())
    held = TaskLock.named(raw, settings.ingest.queue_prefix, "update_progress", 10)
    assert held.acquire()
    assert daemon.cycle() is None
    held.release()
    stats = daemon.cycle()
    assert stats is not None and stats.documents >= 1
    other = RollUpDaemon(cfg, queue, threading.Event())
    assert raw.exists(f"{settings.ingest.queue_prefix}.lock.update_progress") == 0, "the lock is released after a cycle"
    assert other.cycle() is not None


# ----------------------------------------------------------------------------- reconciler


def stream_ids(raw: valkey.Valkey, prefix: str) -> list[str]:
    import json

    return [json.loads(fields[b"message"])["task_id"] for _, fields in raw.xrange(f"{prefix}.0.common")]


def test_a_stranded_task_is_published_again_once(world, env):
    settings, queue, raw = env
    doc, (a,) = running_doc(world)
    set_task(a, 0.2, "10:00:01  working")
    age_task(a, 3600)
    cfg = dataclasses.replace(world.settings, ingest=settings.ingest)
    assert reconcile_once(cfg, queue) >= 1
    assert a in stream_ids(raw, settings.ingest.queue_prefix)
    assert reconcile_once(cfg, queue) == 0, "the update time was touched"


def test_a_task_whose_lock_is_held_is_not_published(world, env):
    settings, queue, raw = env
    doc, (a,) = running_doc(world)
    set_task(a, 0.2, "10:00:01  working")
    age_task(a, 3600)
    lock = TaskLock(raw, a, 30, prefix=settings.ingest.queue_prefix)
    assert lock.acquire()
    cfg = dataclasses.replace(world.settings, ingest=settings.ingest)
    reconcile_once(cfg, queue)
    assert a not in stream_ids(raw, settings.ingest.queue_prefix)
    lock.release()


def test_finished_and_cancelled_tasks_are_not_published(world, env):
    settings, queue, raw = env
    done_doc, (done,) = running_doc(world, "d.txt")
    set_task(done, 1.0, "x")
    gone_doc, (gone,) = running_doc(world, "g.txt")
    set_task(gone, 0.2, "x")
    sql("UPDATE `document` SET `run` = '2' WHERE `id` = %s", (gone_doc,))
    for task in (done, gone):
        age_task(task, 3600)
    cfg = dataclasses.replace(world.settings, ingest=settings.ingest)
    reconcile_once(cfg, queue)
    published = stream_ids(raw, settings.ingest.queue_prefix)
    assert done not in published and gone not in published


# ----------------------------------------------------------------------------- watcher


def watcher_for(world, env, task: str, ttl: float = 5):
    settings, queue, raw = env
    cfg = dataclasses.replace(world.settings, ingest=dataclasses.replace(settings.ingest, lock_ttl_seconds=int(ttl)))
    lock = TaskLock(raw, task, ttl, prefix=settings.ingest.queue_prefix)
    assert lock.acquire()
    control = TaskControl()
    return TaskWatcher(cfg, queue, lock, control, task, "te_test"), control, lock, raw, settings


def test_the_watcher_marks_the_lock_lost_when_the_key_disappears(world, env):
    doc, (a,) = running_doc(world)
    watcher, control, lock, raw, settings = watcher_for(world, env, a)
    watcher.start()
    try:
        raw.delete(lock.key)
        assert wait_until(control.lost.is_set, timeout=5 / 3 + 1.5, interval=0.05)
        assert not control.cancel.is_set()
    finally:
        watcher.stop()
    assert not watcher.is_alive()


def test_the_watcher_cancels_when_the_document_stops_running(world, env):
    doc, (a,) = running_doc(world)
    watcher, control, lock, raw, settings = watcher_for(world, env, a)
    watcher.start()
    try:
        sql("UPDATE `document` SET `run` = '2' WHERE `id` = %s", (doc,))
        assert wait_until(control.cancel.is_set, timeout=settings.ingest.cancel_poll_seconds + 1.5, interval=0.05)
    finally:
        watcher.stop()
        lock.release()


def test_the_watcher_cancels_when_the_task_row_is_deleted(world, env):
    doc, (a,) = running_doc(world)
    watcher, control, lock, raw, settings = watcher_for(world, env, a)
    watcher.start()
    try:
        sql("DELETE FROM `task` WHERE `id` = %s", (a,))
        assert wait_until(control.cancel.is_set, timeout=settings.ingest.cancel_poll_seconds + 1.5, interval=0.05)
    finally:
        watcher.stop()
        lock.release()


def test_the_watcher_renews_and_beats_while_the_task_is_healthy(world, env):
    doc, (a,) = running_doc(world)
    beats: list[int] = []
    settings, queue, raw = env
    watcher, control, lock, raw, settings = watcher_for(world, env, a, ttl=3)
    watcher._on_beat = lambda: beats.append(1)
    watcher.start()
    try:
        assert wait_until(lambda: beats, timeout=5, interval=0.05)
        assert wait_until(lambda: raw.ttl(lock.key) >= 2, timeout=5, interval=0.05), "renewal reset the TTL"
        assert not control.lost.is_set() and not control.cancel.is_set()
    finally:
        watcher.stop()
        lock.release()


def test_an_exception_in_a_poll_is_logged_and_the_thread_goes_on(world, env, monkeypatch):
    doc, (a,) = running_doc(world)
    calls: list[int] = []

    def flaky(task_id):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return True, "1"

    monkeypatch.setattr(task_service, "watch_state", flaky)
    watcher, control, lock, raw, settings = watcher_for(world, env, a)
    watcher.start()
    try:
        assert wait_until(lambda: len(calls) >= 2, timeout=5, interval=0.05)
        assert watcher.is_alive()
    finally:
        watcher.stop()
        lock.release()
