"""One watcher thread per running task (plan 04-12; ING-10, ING-12, D-06, R-156).

Three duties on their own deadlines: renew the task lock every TTL/3, poll MySQL every ``cancel_poll_seconds`` for a task or document that is gone or
no longer running, and beat (queue heartbeat plus the caller's ``on_beat``, which touches the alive file). The thread body catches every exception,
logs its class name and carries on, so a transient outage never kills the watcher. A renewal that finds another owner sets ``control.lost``.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from api.db.services import task_service
from common.ingest_codes import RUN_RUNNING
from common.settings import Settings
from rag.queue.queue_base import TaskQueue
from rag.svr.control import LockLost, TaskControl
from rag.svr.task_lock import TaskLock

logger = logging.getLogger(__name__)

BEAT_SECONDS = 5.0


class TaskWatcher(threading.Thread):
    def __init__(
        self,
        settings: Settings,
        queue: TaskQueue,
        lock: TaskLock,
        control: TaskControl,
        task_id: str,
        consumer: str,
        on_beat: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(name=f"watch-{task_id[:8]}", daemon=True)
        ingest = settings.ingest
        self._queue = queue
        self._lock = lock
        self._control = control
        self._task_id = task_id
        self._consumer = consumer
        self._on_beat = on_beat
        self._renew_every = max(ingest.lock_ttl_seconds / 3, 0.2)
        self._poll_every = max(float(ingest.cancel_poll_seconds), 0.1)
        self._beat_every = min(BEAT_SECONDS, max(ingest.worker_heartbeat_timeout / 4, 0.5))
        self._period = min(self._renew_every, self._poll_every, self._beat_every)
        self._halt = threading.Event()

    def stop(self) -> None:
        self._halt.set()
        if self.is_alive() and threading.current_thread() is not self:
            self.join(10)

    def _renew(self) -> bool:
        """False once the lock is lost (nothing more to renew)."""
        try:
            self._lock.renew()
        except LockLost:
            logger.warning("task lock lost", extra={"task": self._task_id})
            self._control.lost.set()
            return False
        return True

    def _poll(self) -> None:
        exists, run = task_service.watch_state(self._task_id)
        if not exists or run != RUN_RUNNING:
            self._control.cancel.set()

    def _beat(self) -> None:
        self._queue.heartbeat(self._consumer)
        if self._on_beat is not None:
            self._on_beat()

    def run(self) -> None:
        now = time.monotonic()
        due = {"renew": now + self._renew_every, "poll": now + self._poll_every, "beat": now}
        every = {"renew": self._renew_every, "poll": self._poll_every, "beat": self._beat_every}
        while not self._halt.wait(self._period):
            for duty in ("renew", "poll", "beat"):
                if time.monotonic() < due[duty]:
                    continue
                due[duty] = time.monotonic() + every[duty]
                try:
                    if duty == "renew":
                        if not self._renew():
                            return
                    elif duty == "poll":
                        self._poll()
                    else:
                        self._beat()
                except Exception as exc:  # noqa: BLE001 - a watcher never dies of an outage; the class name is enough
                    logger.warning("watcher duty failed", extra={"task": self._task_id, "duty": duty, "error_type": type(exc).__name__})
