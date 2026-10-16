"""Valkey Streams implementation of :class:`TaskQueue` (plan 04-07, ING-02 to ING-07, ING-10, R-156, R-157).

``XADD`` to ``{prefix}.{priority}.common``; one consumer group; ``XAUTOCLAIM`` (full form: the id-only form drops the cursor in valkey-py) for
takeover; acknowledgement is ``XACK`` then ``XDEL``. Every driver failure becomes :class:`QueueUnavailable` with a fixed message.
"""
from __future__ import annotations

import logging
import time

import valkey
from valkey.exceptions import ResponseError, ValkeyError

from common.settings import Settings
from rag.queue.queue_base import (
    MessageMalformed,
    QueueMessage,
    QueueUnavailable,
    TaskQueue,
    decode_message,
    encode_message,
    queue_name,
)

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT_SECONDS = 5
READ_MARGIN_SECONDS = 5
MAX_READ_BLOCK_MS = 30000
UNAVAILABLE = "task queue unavailable"


class ValkeyStreamQueue(TaskQueue):
    def __init__(self, settings: Settings, block_ms: int = MAX_READ_BLOCK_MS) -> None:
        rd = settings.redis
        ing = settings.ingest
        self._prefix = ing.queue_prefix
        self._group = ing.consumer_group
        self._hb_timeout = ing.worker_heartbeat_timeout
        self._high = queue_name(self._prefix, 1)
        self._normal = queue_name(self._prefix, 0)
        self._client = valkey.Valkey(
            host=rd.host,
            port=rd.port,
            password=rd.password or None,
            db=rd.db,
            decode_responses=True,
            socket_timeout=block_ms / 1000 + READ_MARGIN_SECONDS,
            socket_connect_timeout=CONNECT_TIMEOUT_SECONDS,
        )

    # -- helpers -------------------------------------------------------------------------------------------------
    def _hb_key(self, consumer: str) -> str:
        return f"{self._prefix}.hb.{consumer}"

    @property
    def _members_key(self) -> str:
        return f"{self._prefix}.TASKEXE"

    def ping(self) -> None:
        try:
            self._client.ping()
        except (ValkeyError, OSError):
            raise QueueUnavailable(UNAVAILABLE) from None

    def ensure_group(self) -> None:
        try:
            for stream in (self._high, self._normal):
                try:
                    self._client.xgroup_create(stream, self._group, id="0", mkstream=True)
                except ResponseError as exc:
                    if "BUSYGROUP" not in str(exc):
                        raise
        except (ValkeyError, OSError):
            raise QueueUnavailable(UNAVAILABLE) from None

    def _convert(self, stream: str, entries: list, delivered: int | None) -> list[QueueMessage]:
        out: list[QueueMessage] = []
        for message_id, fields in entries:
            try:
                task_id, digest = decode_message(fields)
            except MessageMalformed:
                logger.warning("dropping malformed queue entry stream=%s id=%s", stream, message_id)
                self._drop(stream, message_id)
                continue
            count = delivered if delivered is not None else self._delivery_count(stream, message_id)
            out.append(QueueMessage(queue=stream, message_id=message_id, task_id=task_id, digest=digest, delivered=count))
        return out

    def _drop(self, stream: str, message_id: str) -> None:
        pipe = self._client.pipeline(transaction=True)
        pipe.xack(stream, self._group, message_id)
        pipe.xdel(stream, message_id)
        pipe.execute()

    def _delivery_count(self, stream: str, message_id: str) -> int:
        rows = self._client.xpending_range(stream, self._group, min=message_id, max=message_id, count=1)
        return int(rows[0]["times_delivered"]) if rows else 1

    def _guarded(self, call):
        """Run ``call``; recreate a missing group once; map failures to :class:`QueueUnavailable`."""
        try:
            try:
                return call()
            except ResponseError as exc:
                if "NOGROUP" not in str(exc):
                    raise
                self.ensure_group()
                return call()
        except QueueUnavailable:
            raise
        except (ValkeyError, OSError):
            raise QueueUnavailable(UNAVAILABLE) from None

    # -- TaskQueue -----------------------------------------------------------------------------------------------
    def enqueue(self, task_id: str, digest: str, priority: int = 0) -> str:
        if priority not in (0, 1):
            raise ValueError("priority must be 0 or 1")
        body = encode_message(task_id, digest)
        try:
            return str(self._client.xadd(queue_name(self._prefix, priority), body))
        except (ValkeyError, OSError):
            raise QueueUnavailable(UNAVAILABLE) from None

    def read(self, consumer: str, count: int = 1, block_ms: int = 1000) -> list[QueueMessage]:
        block = max(1, min(block_ms, MAX_READ_BLOCK_MS))

        def first():
            return self._client.xreadgroup(self._group, consumer, {self._high: ">"}, count=count)

        def second():
            return self._client.xreadgroup(self._group, consumer, {self._high: ">", self._normal: ">"}, count=count, block=block)

        result = self._guarded(first) or self._guarded(second)
        out: list[QueueMessage] = []
        for stream, entries in sorted(result or [], key=lambda item: item[0] != self._high):
            out.extend(self._guarded_convert(stream, entries, 1))
        return out[:count]

    def _guarded_convert(self, stream: str, entries: list, delivered: int | None) -> list[QueueMessage]:
        try:
            return self._convert(stream, entries, delivered)
        except (ValkeyError, OSError):
            raise QueueUnavailable(UNAVAILABLE) from None

    def claim_idle(self, consumer: str, min_idle_ms: int, count: int = 10) -> list[QueueMessage]:
        out: list[QueueMessage] = []
        for stream in (self._high, self._normal):

            def claim(stream=stream):
                return self._client.xautoclaim(stream, self._group, consumer, min_idle_time=min_idle_ms, start_id="0-0", count=count)

            result = self._guarded(claim)
            entries = [(mid, fields) for mid, fields in (result[1] or []) if fields is not None]
            out.extend(self._guarded_convert(stream, entries, None))
        return out

    def ack(self, message: QueueMessage) -> None:
        try:
            self._drop(message.queue, message.message_id)
        except (ValkeyError, OSError):
            raise QueueUnavailable(UNAVAILABLE) from None

    def heartbeat(self, consumer: str) -> None:
        now = time.time()
        key = self._hb_key(consumer)
        try:
            pipe = self._client.pipeline(transaction=True)
            pipe.zadd(key, {str(now): now})
            pipe.zremrangebyscore(key, 0, now - self._hb_timeout)
            pipe.expire(key, 2 * self._hb_timeout)
            pipe.sadd(self._members_key, consumer)
            pipe.execute()
        except (ValkeyError, OSError):
            raise QueueUnavailable(UNAVAILABLE) from None

    def live_consumers(self, timeout_seconds: int) -> list[str]:
        cutoff = time.time() - timeout_seconds
        live: list[str] = []
        try:
            for name in sorted(self._client.smembers(self._members_key)):
                newest = self._client.zrevrange(self._hb_key(name), 0, 0, withscores=True)
                if newest and newest[0][1] > cutoff:
                    live.append(name)
        except (ValkeyError, OSError):
            raise QueueUnavailable(UNAVAILABLE) from None
        return live

    def drop_consumer(self, consumer: str) -> None:
        try:
            pipe = self._client.pipeline(transaction=True)
            pipe.delete(self._hb_key(consumer))
            pipe.srem(self._members_key, consumer)
            pipe.execute()
        except (ValkeyError, OSError):
            raise QueueUnavailable(UNAVAILABLE) from None

    def close(self) -> None:
        self._client.close()
