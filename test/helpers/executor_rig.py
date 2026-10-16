"""In-process executors, roll-up daemon and queue for the executor suites (plan 04-12).

Executors run in threads of the test process with a unique queue prefix and consumer group and tiny TTLs, over the stack's real MySQL, Valkey,
Elasticsearch and MinIO and the loopback embedding provider. Nothing here is a hook inside product code: tests read counters the executor keeps
anyway and set the events the signal handler would set.
"""

from __future__ import annotations

import dataclasses
import secrets
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import valkey

from api.db.services import ingestion_service as ing
from common.settings import Settings
from rag.queue.valkey_streams import ValkeyStreamQueue
from rag.svr.executor_loop import Executor
from rag.svr.progress import RollUpDaemon
from test.helpers.ingest import World
from test.integration.test_knowledgebase_service import principal_of

DEFAULTS: dict[str, Any] = {
    "lock_ttl_seconds": 5,
    "reclaim_idle_ms": 10000,
    "reclaim_interval_seconds": 1,
    "progress_interval_seconds": 1,
    "retry_backoff_max_seconds": 1,
    "cancel_poll_seconds": 1,
    "reconcile_after_seconds": 3600,
}


class Runner:
    def __init__(self, rig: Rig) -> None:
        self.executor = Executor(rig.settings, rig.queue, rig.world.deps(settings=rig.settings))
        self.thread = threading.Thread(target=self.executor.run_forever, name=f"exec-{len(rig.runners)}", daemon=True)

    def start(self) -> Runner:
        self.thread.start()
        return self

    def stop(self, timeout: float = 20) -> bool:
        """Ask for a stop and wait; True when the loop returned."""
        self.executor.request_stop()
        if self.thread.is_alive():
            self.thread.join(timeout)
        return not self.thread.is_alive()


class Rig:
    def __init__(self, world: World, **ingest: Any) -> None:
        base = world.settings
        values = {**DEFAULTS, **ingest, "queue_prefix": f"ex{secrets.token_hex(6)}", "consumer_group": f"g{secrets.token_hex(4)}"}
        self.world = world
        self.settings: Settings = dataclasses.replace(base, ingest=dataclasses.replace(base.ingest, **values))
        rd = self.settings.redis
        self.raw = valkey.Valkey(host=rd.host, port=rd.port, password=rd.password or None, db=rd.db, socket_timeout=3, socket_connect_timeout=3)
        self.queue = ValkeyStreamQueue(self.settings)
        self.queue.ensure_group()
        self.runners: list[Runner] = []
        self._rollup: tuple[RollUpDaemon, threading.Event] | None = None

    @property
    def prefix(self) -> str:
        return self.settings.ingest.queue_prefix

    @property
    def group(self) -> str:
        return self.settings.ingest.consumer_group

    def executor(self) -> Runner:
        runner = Runner(self)
        self.runners.append(runner)
        return runner

    def start_executor(self) -> Runner:
        return self.executor().start()

    def start_rollup(self) -> None:
        if self._rollup is None:
            stop = threading.Event()
            daemon = RollUpDaemon(self.settings, self.queue, stop)
            daemon.start()
            self._rollup = (daemon, stop)

    def parse(self, *doc_ids: str) -> None:
        who = principal_of(self.world.owner)
        visible = ing.authorize_parse(who, self.world.dataset.id)
        ing.start_parse(self.settings, visible, who, list(doc_ids), True, queue=self.queue)

    def cancel(self, *doc_ids: str) -> list[str]:
        who = principal_of(self.world.owner)
        visible = ing.authorize_parse(who, self.world.dataset.id)
        return ing.cancel_parse(self.settings, visible, who, list(doc_ids))

    def stream_length(self) -> int:
        return sum(int(self.raw.xlen(f"{self.prefix}.{p}.common")) for p in (0, 1))

    def pending(self) -> int:
        total = 0
        for p in (0, 1):
            try:
                total += int(self.raw.xpending(f"{self.prefix}.{p}.common", self.group)["pending"])
            except valkey.ResponseError:
                continue
        return total

    def drained(self) -> bool:
        return self.stream_length() == 0 and self.pending() == 0

    def close(self) -> None:
        for runner in self.runners:
            runner.stop()
        if self._rollup is not None:
            self._rollup[1].set()
            self._rollup[0].join(10)
        for key in self.raw.scan_iter(match=self.prefix + "*"):
            self.raw.delete(key)
        self.queue.close()
        self.raw.close()


@contextmanager
def rig_for(world: World, **ingest: Any) -> Iterator[Rig]:
    rig = Rig(world, **ingest)
    try:
        yield rig
    finally:
        rig.close()
