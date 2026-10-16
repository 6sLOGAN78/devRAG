"""Cancellation and lock-loss signals for one running task (ING-12, D-06).

``TaskControl`` carries three events set by the executor: ``cancel`` (the user cancelled), ``lost`` (the task lock was lost) and ``shutdown``
(the worker is stopping). The pipeline
calls :meth:`TaskControl.check` between steps and uses :func:`wait_for` around blocking calls so a cancel is noticed without waiting for the call.
"""

from __future__ import annotations

import threading
from concurrent.futures import Future
from concurrent.futures import wait as futures_wait
from typing import TypeVar

T = TypeVar("T")
POLL_SECONDS = 0.25


class TaskCancelled(Exception):
    """The task was cancelled, replaced or deleted; stop without marking failure."""


class ShutdownRequested(TaskCancelled):
    """The worker was asked to stop; the task is handed on rather than cancelled."""


class LockLost(Exception):
    """The lock is no longer held by this owner (expired or taken over)."""


class TaskControl:
    def __init__(self) -> None:
        self.cancel = threading.Event()
        self.lost = threading.Event()
        self.shutdown = threading.Event()

    def stopped(self) -> bool:
        return self.lost.is_set() or self.shutdown.is_set() or self.cancel.is_set()

    def check(self) -> None:
        if self.lost.is_set():
            raise LockLost("task lock lost")
        if self.shutdown.is_set():
            raise ShutdownRequested("worker is shutting down")
        if self.cancel.is_set():
            raise TaskCancelled("task cancelled")


def wait_for(future: Future[T], control: TaskControl) -> T:
    """Result of ``future``; on cancel or lost lock the future is abandoned (its result discarded) and the signal raised at once."""
    while True:
        done, _ = futures_wait([future], timeout=POLL_SECONDS)
        if done:
            return future.result()
        if control.stopped():
            future.cancel()
            control.check()
