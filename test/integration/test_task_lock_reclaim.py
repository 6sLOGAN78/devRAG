"""Task lock and reclaim without double processing, on the stack's real Valkey (plan 04-07, ING-05, ING-06, R-12, R-156)."""
from __future__ import annotations

import dataclasses
import secrets
from collections.abc import Iterator

import pytest
import valkey

from common.settings import Settings, load_settings
from rag.queue.valkey_streams import ValkeyStreamQueue
from rag.svr.task_lock import LockLost, TaskLock, lock_key
from test.helpers.wait import wait_until

pytestmark = pytest.mark.integration

TASK = "b" * 32


@pytest.fixture
def env() -> Iterator[tuple[Settings, ValkeyStreamQueue, valkey.Valkey]]:
    base = load_settings()
    prefix = f"tl{secrets.token_hex(6)}"
    settings = dataclasses.replace(base, ingest=dataclasses.replace(base.ingest, queue_prefix=prefix, consumer_group=f"g{secrets.token_hex(4)}"))
    rd = settings.redis
    raw = valkey.Valkey(host=rd.host, port=rd.port, password=rd.password or None, db=rd.db, socket_timeout=3, socket_connect_timeout=3)
    queue = ValkeyStreamQueue(settings)
    yield settings, queue, raw
    for key in raw.scan_iter(match=prefix + "*"):
        raw.delete(key)
    assert list(raw.scan_iter(match=prefix + "*")) == []
    queue.close()
    raw.close()


def make(env, ttl: float = 30) -> TaskLock:
    settings, _, raw = env
    return TaskLock(raw, TASK, ttl, prefix=settings.ingest.queue_prefix)


def test_second_acquire_fails_and_key_is_namespaced(env):
    settings, _, raw = env
    a, b = make(env), make(env)
    assert a.acquire() is True
    assert b.acquire() is False
    assert raw.exists(lock_key(settings.ingest.queue_prefix, TASK))
    assert a.holds_lock() and not b.holds_lock()


def test_release_is_compare_and_delete(env):
    a, b = make(env), make(env)
    assert a.acquire()
    assert b.release() is False
    assert a.holds_lock()
    assert a.release() is True
    assert b.acquire()


def test_renew_raises_when_the_token_changed(env):
    settings, _, raw = env
    a, b = make(env), make(env)
    assert a.acquire()
    a.renew()
    raw.delete(lock_key(settings.ingest.queue_prefix, TASK))
    assert b.acquire()
    with pytest.raises(LockLost):
        a.renew()


def test_lock_expires_without_renewal(env):
    a, b = make(env, ttl=2), make(env, ttl=2)
    assert a.acquire()
    assert b.acquire() is False
    assert wait_until(b.acquire, timeout=10, interval=0.25)


def test_live_owner_is_not_double_processed(env):
    settings, queue, _ = env
    queue.enqueue(TASK, "d")
    msg = queue.read("a", count=1, block_ms=100)[0]
    lock_a = make(env)
    assert lock_a.acquire()
    claimed = queue.claim_idle("b", min_idle_ms=0)
    assert [m.message_id for m in claimed] == [msg.message_id]
    lock_b = make(env)
    assert lock_b.acquire() is False
    stream = msg.queue
    assert queue._client.xpending(stream, settings.ingest.consumer_group)["pending"] == 1
    lock_a.release()
    queue.ack(msg)
    assert queue._client.xlen(stream) == 0
    assert make(env).acquire()


def test_expired_owner_is_reclaimed_and_completed_once(env):
    settings, queue, _ = env
    queue.enqueue(TASK, "d")
    msg = queue.read("a", count=1, block_ms=100)[0]
    lock_a = make(env, ttl=2)
    assert lock_a.acquire()
    lock_b = make(env, ttl=2)
    assert wait_until(lock_b.acquire, timeout=10, interval=0.25)
    claimed = queue.claim_idle("b", min_idle_ms=0)
    assert [m.message_id for m in claimed] == [msg.message_id]
    queue.ack(claimed[0])
    lock_b.release()
    assert queue._client.xlen(msg.queue) == 0
    assert queue._client.xpending(msg.queue, settings.ingest.consumer_group)["pending"] == 0
