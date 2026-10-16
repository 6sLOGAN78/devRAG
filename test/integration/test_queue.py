"""Valkey Streams task queue against the stack's real Valkey (plan 04-07, ING-02..ING-07, ING-10, R-156, R-157).

Every test uses its own queue prefix and consumer group so the running executor never sees these messages.
"""
from __future__ import annotations

import dataclasses
import secrets
from collections.abc import Iterator

import pytest
import valkey

from common.settings import RedisSettings, Settings, load_settings
from rag.queue.queue_base import QueueUnavailable
from rag.queue.valkey_streams import ValkeyStreamQueue
from test.helpers.wait import wait_until

pytestmark = pytest.mark.integration


def _raw(settings: Settings) -> valkey.Valkey:
    rd = settings.redis
    return valkey.Valkey(host=rd.host, port=rd.port, password=rd.password or None, db=rd.db, socket_timeout=3, socket_connect_timeout=3, decode_responses=True)


@pytest.fixture
def env() -> Iterator[tuple[Settings, ValkeyStreamQueue, valkey.Valkey]]:
    base = load_settings()
    prefix = f"tq{secrets.token_hex(6)}"
    settings = dataclasses.replace(base, ingest=dataclasses.replace(base.ingest, queue_prefix=prefix, consumer_group=f"g{secrets.token_hex(4)}"))
    queue = ValkeyStreamQueue(settings)
    raw = _raw(settings)
    yield settings, queue, raw
    for key in raw.scan_iter(match=prefix + "*"):
        raw.delete(key)
    assert list(raw.scan_iter(match=prefix + "*")) == []
    queue.close()
    raw.close()


def t(n: int) -> str:
    return f"{n:032x}"


def test_enqueue_lands_on_the_priority_stream(env):
    settings, queue, raw = env
    prefix = settings.ingest.queue_prefix
    mid = queue.enqueue(t(1), "d", priority=1)
    assert mid
    assert raw.xlen(f"{prefix}.1.common") == 1
    assert raw.xlen(f"{prefix}.0.common") == 0
    with pytest.raises(ValueError):
        queue.enqueue(t(2), "d", priority=2)


def test_high_priority_is_read_first(env):
    _, queue, _ = env
    queue.enqueue(t(1), "d", priority=0)
    queue.enqueue(t(2), "d", priority=1)
    first = queue.read("c1", count=1, block_ms=100)
    second = queue.read("c1", count=1, block_ms=100)
    assert [m.task_id for m in first] == [t(2)]
    assert [m.task_id for m in second] == [t(1)]
    assert first[0].delivered == 1


def test_two_consumers_never_share_a_message(env):
    _, queue, _ = env
    for i in range(10):
        queue.enqueue(t(i), "d")
    got: list[str] = []
    while True:
        batch = queue.read("a", count=2, block_ms=50) + queue.read("b", count=2, block_ms=50)
        if not batch:
            break
        got.extend(m.message_id for m in batch)
    assert len(got) == 10
    assert len(set(got)) == 10


def test_reclaim_then_late_ack_by_the_original_owner(env):
    settings, queue, raw = env
    queue.enqueue(t(1), "d")
    msg = queue.read("a", count=1, block_ms=100)[0]
    assert queue.claim_idle("b", min_idle_ms=3_600_000) == []
    claimed = queue.claim_idle("b", min_idle_ms=0)
    assert [m.message_id for m in claimed] == [msg.message_id]
    assert claimed[0].delivered == 2
    queue.ack(msg)
    stream = f"{settings.ingest.queue_prefix}.0.common"
    assert raw.xpending(stream, settings.ingest.consumer_group)["pending"] == 0
    assert raw.xlen(stream) == 0


def test_missing_group_is_recreated(env):
    settings, queue, raw = env
    queue.ensure_group()
    for p in (0, 1):
        raw.delete(f"{settings.ingest.queue_prefix}.{p}.common")
    assert queue.read("a", count=1, block_ms=50) == []
    queue.enqueue(t(5), "d")
    assert [m.task_id for m in queue.read("a", count=1, block_ms=100)] == [t(5)]


def test_malformed_entry_is_dropped(env):
    settings, queue, raw = env
    stream = f"{settings.ingest.queue_prefix}.0.common"
    queue.ensure_group()
    raw.xadd(stream, {"message": "garbage"})
    queue.enqueue(t(7), "d")
    got = queue.read("a", count=5, block_ms=100)
    assert [m.task_id for m in got] == [t(7)]
    queue.ack(got[0])
    assert raw.xlen(stream) == 0


def test_outage_is_a_typed_error_naming_no_host(env):
    settings, _, _ = env
    dead = dataclasses.replace(settings, redis=RedisSettings(host="localhost", port=1, password="secret-pw", db=0))
    queue = ValkeyStreamQueue(dead)
    with pytest.raises(QueueUnavailable) as caught:
        queue.enqueue(t(1), "d")
    text = str(caught.value)
    assert "localhost" not in text and "secret-pw" not in text and ":1" not in text
    queue.close()


def test_heartbeat_has_ttl_and_listing(env):
    settings, queue, raw = env
    queue.heartbeat("w1")
    key = f"{settings.ingest.queue_prefix}.hb.w1"
    assert raw.ttl(key) > 0
    assert "w1" in queue.live_consumers(timeout_seconds=60)
    assert wait_until(lambda: "w1" not in queue.live_consumers(timeout_seconds=0), timeout=5, interval=0.2)
    queue.drop_consumer("w1")
    assert not raw.exists(key)
