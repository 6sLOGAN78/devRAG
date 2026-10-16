"""The executor: collect, gate on the task lock, run, retry, fail, hand on (plan 04-12; ING-04..07, ING-10..12, D-05, D-25, R-156..158).

``handle_message`` never trusts the message: tenant, document and page range come from MySQL. Order for every message, new or reclaimed: reload the
rows (drop and acknowledge a gone task, a digest that differs from the row or a document that is not running), take the task lock (a live owner
leaves the message pending), count the attempt under the lock (a crashed task that used every attempt fails ``worker_lost``), start the watcher, run
the pipeline inside ``task_limiter``, then record done, cancelled, lost, shutdown or failure. A message is acknowledged only once the task row is final
or a fresh message has been published. The loop survives Valkey, MySQL and stream outages: it logs the class name, waits and carries on.
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
import uuid
from collections import Counter
from enum import Enum

import valkey

from api.db.services import task_service
from api.db.services.task_service import TaskContext
from common.ingest_codes import RUN_RUNNING
from common.settings import Settings
from rag.queue.queue_base import QueueMessage, TaskQueue
from rag.svr import healthcheck
from rag.svr.control import LockLost, ShutdownRequested, TaskCancelled, TaskControl
from rag.svr.embedding import release_database_connection
from rag.svr.failure import TaskFailure, classify
from rag.svr.heartbeat import TaskWatcher
from rag.svr.pipeline import PipelineDeps, PipelineResult, run_pipeline
from rag.svr.task_lock import TaskLock, open_client

logger = logging.getLogger(__name__)

BEAT_SECONDS = 5.0
READ_BLOCK_MS = 1000
OUTAGE_WAIT_SECONDS = 2.0
BACKOFF_STEP_SECONDS = 0.25


class Outcome(Enum):
    DONE = "done"
    FAILED = "failed"
    WORKER_LOST = "worker_lost"
    RETRIED = "retried"
    CANCELLED = "cancelled"
    LOST = "lost"
    SHUTDOWN = "shutdown"
    DROPPED = "dropped"
    DEFERRED = "deferred"


def consumer_name() -> str:
    return f"te_{socket.gethostname()[:20]}_{os.getpid()}_{uuid.uuid4().hex[:6]}"


class Executor:
    def __init__(self, settings: Settings, queue: TaskQueue, deps: PipelineDeps, *, name: str | None = None, client: valkey.Valkey | None = None) -> None:
        self.settings = settings
        self.queue = queue
        self.deps = deps
        self.name = name or consumer_name()
        self.stop = threading.Event()
        self.outcomes: Counter[Outcome] = Counter()
        self.last_error = 0
        self.last_error_type = ""
        self._client = client if client is not None else open_client(settings)
        self._owns_client = client is None
        self._guard = threading.Lock()
        self._control: TaskControl | None = None

    # -- stopping ------------------------------------------------------------------------------------------------
    def interrupt_all(self) -> None:
        """Ask the running task to stop at its next checkpoint (used by the signal handler)."""
        with self._guard:
            if self._control is not None:
                self._control.shutdown.set()

    def request_stop(self) -> None:
        self.stop.set()
        self.interrupt_all()

    # -- one message ---------------------------------------------------------------------------------------------
    def handle_message(self, message: QueueMessage) -> Outcome:
        try:
            outcome = self._handle(message)
        finally:
            release_database_connection()
        self.outcomes[outcome] += 1
        return outcome

    def _handle(self, message: QueueMessage) -> Outcome:
        ingest = self.settings.ingest
        ctx = task_service.load_task_context(message.task_id)
        if ctx is None or ctx.digest != message.digest or ctx.doc_run != RUN_RUNNING:
            self.queue.ack(message)
            return Outcome.DROPPED
        lock = TaskLock(self._client, message.task_id, ingest.lock_ttl_seconds, prefix=ingest.queue_prefix)
        if not lock.acquire():
            return Outcome.DEFERRED
        try:
            return self._locked(message, lock)
        finally:
            lock.release()

    def _locked(self, message: QueueMessage, lock: TaskLock) -> Outcome:
        cap = self.settings.ingest.max_attempts
        claim = task_service.claim_attempt(message.task_id, cap)
        if claim.outcome in (task_service.GONE, task_service.FINISHED):
            self.queue.ack(message)
            return Outcome.DROPPED
        if claim.outcome == task_service.EXHAUSTED:
            task_service.mark_task_failed(message.task_id, TaskFailure("parse", "worker_lost").line())
            self.queue.ack(message)
            return Outcome.WORKER_LOST
        ctx = task_service.load_task_context(message.task_id)
        if ctx is None:
            self.queue.ack(message)
            return Outcome.DROPPED
        control = TaskControl()
        if self.stop.is_set():
            control.shutdown.set()
        with self._guard:
            self._control = control
        watcher = TaskWatcher(self.settings, self.queue, lock, control, message.task_id, self.name, healthcheck.touch_alive)
        watcher.start()
        try:
            return self._run(message, ctx, lock, control, claim.attempt)
        finally:
            watcher.stop()
            with self._guard:
                self._control = None

    def _run(self, message: QueueMessage, ctx: TaskContext, lock: TaskLock, control: TaskControl, attempt: int) -> Outcome:
        began = time.monotonic()
        try:
            result = self._pipeline(ctx, control)
            control.check()
        except ShutdownRequested:
            return self._hand_on(message, ctx, lock, refund=True)
        except TaskCancelled:
            self.queue.ack(message)
            return Outcome.CANCELLED
        except LockLost:
            logger.warning("task lock lost, leaving the message pending", extra={"task": ctx.task_id})
            return Outcome.LOST
        except Exception as exc:  # noqa: BLE001 - every failure is classified once, here
            return self._failed(message, ctx, lock, control, classify(exc, "parse"), attempt)
        task_service.mark_task_done(ctx.task_id, result.chunk_ids, time.monotonic() - began)
        self.queue.ack(message)
        return Outcome.DONE

    def _pipeline(self, ctx: TaskContext, control: TaskControl) -> PipelineResult:
        limiter = self.deps.limiters.task_limiter
        while not limiter.acquire(timeout=0.5):
            control.check()
        try:
            return run_pipeline(ctx, control, self.deps)
        finally:
            limiter.release()

    def _failed(self, message: QueueMessage, ctx: TaskContext, lock: TaskLock, control: TaskControl, failure: TaskFailure, attempt: int) -> Outcome:
        ingest = self.settings.ingest
        if failure.terminal or attempt >= ingest.max_attempts:
            task_service.mark_task_failed(ctx.task_id, failure.line())
            self.queue.ack(message)
            return Outcome.FAILED
        plain = failure.message.rstrip(".")
        task_service.set_progress(ctx.task_id, 0.0, f"Attempt {attempt} of {ingest.max_attempts} did not finish: {plain}. Trying again.")
        deadline = time.monotonic() + min(ingest.retry_backoff_max_seconds, 2**attempt * 2)
        while not self.stop.is_set() and not control.stopped() and time.monotonic() < deadline:
            self.stop.wait(min(BACKOFF_STEP_SECONDS, max(deadline - time.monotonic(), 0.0)))
        if control.lost.is_set():
            return Outcome.LOST
        if control.cancel.is_set():
            self.queue.ack(message)
            return Outcome.CANCELLED
        return self._hand_on(message, ctx, lock, refund=False, outcome=Outcome.SHUTDOWN if self.stop.is_set() else Outcome.RETRIED)

    def _hand_on(self, message: QueueMessage, ctx: TaskContext, lock: TaskLock, *, refund: bool, outcome: Outcome = Outcome.SHUTDOWN) -> Outcome:
        """Publish a fresh message, then acknowledge the old one. The lock is released first so the next reader is not turned away."""
        if refund:
            task_service.refund_attempt(ctx.task_id)
        lock.release()
        self.queue.enqueue(ctx.task_id, ctx.digest, 0)
        self.queue.ack(message)
        return outcome

    # -- the loop ------------------------------------------------------------------------------------------------
    def run_forever(self) -> None:
        self._safe_ensure_group()
        next_beat = next_reclaim = 0.0
        while not self.stop.is_set():
            try:
                healthcheck.touch_alive()
                now = time.monotonic()
                if now >= next_beat:
                    self.queue.heartbeat(self.name)
                    next_beat = now + BEAT_SECONDS
                if now >= next_reclaim:
                    next_reclaim = now + self.settings.ingest.reclaim_interval_seconds
                    for message in self.queue.claim_idle(self.name, self.settings.ingest.reclaim_idle_ms):
                        self.handle_message(message)
                for message in self.queue.read(self.name, count=1, block_ms=READ_BLOCK_MS):
                    self.handle_message(message)
            except Exception as exc:  # noqa: BLE001 - outages (queue, database, stream) and surprises never end the loop (R-157)
                self.last_error += 1
                self.last_error_type = type(exc).__name__
                logger.warning("executor loop error", extra={"error_type": self.last_error_type})
                self.stop.wait(OUTAGE_WAIT_SECONDS)
                self._safe_ensure_group()
        self._close()

    def _safe_ensure_group(self) -> None:
        try:
            self.queue.ensure_group()
        except Exception as exc:  # noqa: BLE001
            logger.warning("consumer group not ready", extra={"error_type": type(exc).__name__})

    def _close(self) -> None:
        try:
            self.queue.drop_consumer(self.name)
        except Exception as exc:  # noqa: BLE001
            logger.info("consumer not dropped", extra={"error_type": type(exc).__name__})
        if self._owns_client:
            self._client.close()
