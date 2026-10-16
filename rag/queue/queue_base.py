"""Task queue interface, message codec and typed errors (plan 04-07, ING-02, ING-03, D-18).

The message body carries only ``task_id`` and ``digest``; everything else is loaded from MySQL by the worker. Error messages never
contain a host, port or password.
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass

TASK_ID_RE = re.compile(r"[0-9a-f]{32}")
BODY_FIELD = "message"
PRIORITIES = (0, 1)


class QueueUnavailable(Exception):
    """The queue store cannot be reached or refused the call. The message is fixed and names no endpoint."""


class MessageMalformed(Exception):
    """A stream entry is not a valid task message."""


@dataclass(frozen=True)
class QueueMessage:
    queue: str
    message_id: str
    task_id: str
    digest: str
    delivered: int = 1


def queue_name(prefix: str, priority: int) -> str:
    return f"{prefix}.{priority}.common"


def encode_message(task_id: str, digest: str) -> dict[str, str]:
    if not isinstance(task_id, str) or TASK_ID_RE.fullmatch(task_id) is None:
        raise MessageMalformed("invalid task id")
    return {BODY_FIELD: json.dumps({"task_id": task_id, "digest": digest}, separators=(",", ":"))}


def decode_message(fields: Mapping[str, str] | None) -> tuple[str, str]:
    """Return ``(task_id, digest)`` or raise :class:`MessageMalformed`."""
    raw = (fields or {}).get(BODY_FIELD)
    if not isinstance(raw, str):
        raise MessageMalformed("missing body")
    try:
        body = json.loads(raw)
    except ValueError:
        raise MessageMalformed("body is not JSON") from None
    if not isinstance(body, dict) or not set(body) <= {"task_id", "digest"}:
        raise MessageMalformed("unexpected body shape")
    task_id, digest = body.get("task_id"), body.get("digest", "")
    if not isinstance(task_id, str) or TASK_ID_RE.fullmatch(task_id) is None or not isinstance(digest, str):
        raise MessageMalformed("invalid task id")
    return task_id, digest


class TaskQueue(ABC):
    """One durable task stream shared by a worker fleet."""

    @abstractmethod
    def ping(self) -> None:
        """Raise :class:`QueueUnavailable` when the store cannot be reached."""

    @abstractmethod
    def ensure_group(self) -> None:
        """Create the consumer group (and streams) when absent."""

    @abstractmethod
    def enqueue(self, task_id: str, digest: str, priority: int = 0) -> str:
        """Publish a task; returns the message id. ``priority`` is 0 or 1."""

    @abstractmethod
    def read(self, consumer: str, count: int = 1, block_ms: int = 1000) -> list[QueueMessage]:
        """Read new messages, priority 1 first."""

    @abstractmethod
    def claim_idle(self, consumer: str, min_idle_ms: int, count: int = 10) -> list[QueueMessage]:
        """Take over messages pending for at least ``min_idle_ms``."""

    @abstractmethod
    def ack(self, message: QueueMessage) -> None:
        """Acknowledge and delete the entry."""

    @abstractmethod
    def heartbeat(self, consumer: str) -> None:
        """Record that ``consumer`` is alive."""

    @abstractmethod
    def live_consumers(self, timeout_seconds: int) -> list[str]:
        """Consumers whose last heartbeat is newer than ``timeout_seconds``."""

    @abstractmethod
    def drop_consumer(self, consumer: str) -> None:
        """Forget a consumer's heartbeat."""

    @abstractmethod
    def close(self) -> None:
        """Release the connection."""
