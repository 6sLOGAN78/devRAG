"""Owner-token task lock (plan 04-07, ING-06, R-12, R-156).

Wraps ``valkey.lock.Lock`` so the compare-and-delete release and the owner-checked renewal come from the library's own scripts.
The TTL, the renewal period and who calls :meth:`TaskLock.renew` belong to the executor (plan 04-12).
"""
from __future__ import annotations

from types import TracebackType

import valkey
from valkey.exceptions import LockError, LockNotOwnedError, ValkeyError
from valkey.lock import Lock

from rag.queue.queue_base import QueueUnavailable

UNAVAILABLE = "task queue unavailable"


class LockLost(Exception):
    """The lock is no longer held by this owner (expired or taken over)."""


class LockNotAcquired(Exception):
    """The lock is held by another owner."""


def lock_key(prefix: str, task_id: str) -> str:
    return f"{prefix}.lock.task_{task_id}"


class TaskLock:
    def __init__(self, client: valkey.Valkey, task_id: str, ttl_seconds: float, prefix: str = "te") -> None:
        self.key = lock_key(prefix, task_id)
        self._ttl = ttl_seconds
        self._lock = Lock(client, self.key, timeout=ttl_seconds, thread_local=False)

    def acquire(self) -> bool:
        try:
            return bool(self._lock.acquire(blocking=False))
        except (ValkeyError, OSError):
            raise QueueUnavailable(UNAVAILABLE) from None

    def holds_lock(self) -> bool:
        try:
            return bool(self._lock.owned())
        except (ValkeyError, OSError):
            raise QueueUnavailable(UNAVAILABLE) from None

    def renew(self) -> None:
        """Reset the TTL. Raises :class:`LockLost` when the token no longer matches."""
        try:
            if not self._lock.reacquire():
                raise LockLost("task lock lost")
        except LockNotOwnedError:
            raise LockLost("task lock lost") from None
        except LockError:
            raise LockLost("task lock lost") from None
        except (ValkeyError, OSError):
            raise QueueUnavailable(UNAVAILABLE) from None

    def release(self) -> bool:
        """Compare-and-delete. False (and the lock untouched) when this object is not the owner."""
        try:
            self._lock.release()
            return True
        except LockError:
            return False
        except (ValkeyError, OSError):
            raise QueueUnavailable(UNAVAILABLE) from None

    def __enter__(self) -> TaskLock:
        if not self.acquire():
            raise LockNotAcquired("task lock is held")
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self.release()
