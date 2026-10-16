"""Lock loss, reclaim, graceful shutdown, stream loss and a Valkey outage (plan 04-12; ING-05..07, ING-10, R-156..158, D-06).

The lock-loss test deletes the lock key with a plain Valkey client and sets events on executor objects it owns; product code has no test hook.
Waiting is event based; no test sleeps.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from rag.svr.executor_loop import Outcome
from rag.svr.task_lock import lock_key
from test.helpers.accounts import AccountRegistry
from test.helpers.executor_rig import rig_for
from test.helpers.fake_provider import FakeProvider, running_fake_provider
from test.helpers.ingest import (
    World,
    add_document,
    cleanup_tasks,
    doc_state,
    indexed,
    make_pipeline_world,
    paragraphs,
    task_state,
)
from test.helpers.uploads import sql
from test.helpers.wait import wait_until
from test.integration.test_upload_service import _bound_database  # noqa: F401  (autouse module fixture)
from test.testcases.conftest import BASE_URL, compose, service_health

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


def only_task(doc_id: str) -> str:
    (row,) = sql("SELECT `id` FROM `task` WHERE `doc_id` = %s", (doc_id,))
    return row[0]


def finished(doc_id: str, run: str = "3"):
    return lambda: doc_state(doc_id)["run"] == run


def test_a_displaced_worker_stops_and_another_finishes_the_task_without_duplicates(world, fake):
    fake.delay_ms = 400
    doc = add_document(world, "slow.txt", paragraphs(40))
    with rig_for(world, batch_size=2) as rig:
        rig.start_rollup()
        a = rig.start_executor()
        rig.parse(doc)
        task = only_task(doc)
        wait_until(lambda: len(indexed(world, doc_id=[doc])) > 0, timeout=60, interval=0.05)
        rig.raw.delete(lock_key(rig.prefix, task))
        ttl = rig.settings.ingest.lock_ttl_seconds
        wait_until(lambda: a.executor.outcomes[Outcome.LOST] == 1, timeout=ttl / 3 + 2, interval=0.05, describe=lambda: str(a.executor.outcomes))
        assert task_state(task)["progress"] >= 0, "nothing was marked failed"
        kept = len(indexed(world, doc_id=[doc]))
        assert 0 < kept < 40, "chunks already indexed are left alone"
        assert rig.pending() == 1, "the message was not acknowledged"
        assert a.stop()
        b = rig.start_executor()
        wait_until(finished(doc), timeout=120, interval=0.25, describe=lambda: str(doc_state(doc)))
        found = indexed(world, doc_id=[doc])
        assert len(found) == 40
        assert {h["id"] for h in found} == {f"{doc}_{i}" for i in range(40)}
        assert task_state(task)["retry_count"] == 2
        assert b.executor.outcomes[Outcome.DONE] == 1
        wait_until(rig.drained, timeout=10, interval=0.1)


def test_a_live_owner_is_not_processed_twice(world, fake):
    fake.delay_ms = 400
    doc = add_document(world, "owned.txt", paragraphs(40))
    with rig_for(world, batch_size=2, reclaim_idle_ms=2000) as rig:
        rig.start_rollup()
        a = rig.start_executor()
        rig.parse(doc)
        task = only_task(doc)
        wait_until(lambda: len(indexed(world, doc_id=[doc])) > 0, timeout=60, interval=0.05)
        b = rig.start_executor()
        wait_until(lambda: b.executor.outcomes[Outcome.DEFERRED] >= 1, timeout=20, interval=0.1, describe=lambda: str(b.executor.outcomes))
        assert doc_state(doc)["run"] == "1", "still running under its first owner"
        wait_until(finished(doc), timeout=120, interval=0.25, describe=lambda: str(doc_state(doc)))
        assert task_state(task)["retry_count"] == 1
        assert a.executor.outcomes[Outcome.DONE] == 1 and b.executor.outcomes[Outcome.DONE] == 0
        assert len(indexed(world, doc_id=[doc])) == 40
        wait_until(rig.drained, timeout=10, interval=0.1)


def test_a_graceful_shutdown_refunds_the_attempt_and_hands_the_task_on(world, fake):
    fake.delay_ms = 400
    doc = add_document(world, "handoff.txt", paragraphs(40))
    with rig_for(world, batch_size=2) as rig:
        rig.start_rollup()
        a = rig.start_executor()
        rig.parse(doc)
        task = only_task(doc)
        wait_until(lambda: len(indexed(world, doc_id=[doc])) > 0, timeout=60, interval=0.05)
        began = time.monotonic()
        assert a.stop(timeout=rig.settings.ingest.lock_ttl_seconds)
        assert time.monotonic() - began <= rig.settings.ingest.lock_ttl_seconds
        assert a.executor.outcomes[Outcome.SHUTDOWN] == 1
        assert task_state(task)["retry_count"] == 0, "the attempt was refunded"
        assert rig.raw.exists(lock_key(rig.prefix, task)) == 0, "the lock was released"
        assert rig.stream_length() == 1 and rig.pending() == 0, "one fresh message, the old one acknowledged"
        rig.start_executor()
        wait_until(finished(doc), timeout=120, interval=0.25, describe=lambda: str(doc_state(doc)))
        assert task_state(task)["retry_count"] == 1
        assert len(indexed(world, doc_id=[doc])) == 40
        wait_until(rig.drained, timeout=10, interval=0.1)


def test_losing_the_stream_and_the_group_does_not_stop_the_executor(world):
    with rig_for(world) as rig:
        rig.start_rollup()
        runner = rig.start_executor()
        wait_until(lambda: rig.raw.exists(f"{rig.prefix}.0.common") == 1, timeout=10, interval=0.1)
        rig.raw.delete(f"{rig.prefix}.0.common", f"{rig.prefix}.1.common")
        doc = add_document(world, "after.txt", paragraphs(3))
        rig.parse(doc)
        wait_until(finished(doc), timeout=90, interval=0.25, describe=lambda: str(doc_state(doc)))
        assert runner.thread.is_alive()


@contextmanager
def valkey_stopped() -> Iterator[None]:
    out = compose("stop", "redis")
    assert out.returncode == 0, out.stderr
    try:
        yield
    finally:
        started = compose("start", "redis")
        wait_until(lambda: service_health("redis") == "healthy", timeout=180, interval=2)
        wait_until(lambda: service_health("app") == "healthy", timeout=120, interval=2)
        assert started.returncode == 0, started.stderr


@pytest.mark.serial
def test_a_valkey_outage_is_survived_and_work_resumes(world):
    with rig_for(world) as rig:
        rig.start_rollup()
        runner = rig.start_executor()
        before = runner.executor.last_error
        with valkey_stopped():
            wait_until(lambda: runner.executor.last_error > before, timeout=60, interval=0.25)
        assert runner.thread.is_alive()
        doc = add_document(world, "resumed.txt", paragraphs(3))
        rig.parse(doc)
        wait_until(finished(doc), timeout=120, interval=0.5, describe=lambda: str(doc_state(doc)))
        assert runner.thread.is_alive()
