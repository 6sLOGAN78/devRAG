"""Executor process: ``python -m rag.svr.task_executor`` (plan 04-12; ING-04..08, R-156..158).

Boot order: logger (stdout only, so scaled copies never share a log file), database verify (no DDL, no seed), queue ping and group, roll-up daemon
thread, then the executor loop on the main thread. SIGTERM and SIGINT stop taking messages, interrupt the running task at its next checkpoint (it is
handed on with its attempt refunded) and the process exits 0. Exit code 1 only when boot fails.
"""

from __future__ import annotations

import contextlib
import logging
import signal
import sys
import threading
from types import FrameType

import peewee
import pymysql

from api.db.database import DB, init_database
from api.db.migrations.runner import current_version
from common.log_utils import init_root_logger
from common.settings import ConfigError, Settings, get_settings
from rag.queue.factory import get_queue, reset_queue_cache
from rag.queue.queue_base import QueueUnavailable
from rag.svr.embedding import EmbedRunner
from rag.svr.executor_loop import Executor
from rag.svr.limiters import Limiters
from rag.svr.pipeline import PipelineDeps
from rag.svr.progress import RollUpDaemon
from rag.utils.es_conn import get_doc_store
from rag.utils.storage_factory import get_storage

SERVICE_NAME = "task_executor"
logger = logging.getLogger(SERVICE_NAME)
QUIET_LOGGERS = ("elastic_transport", "urllib3", "httpx", "httpcore")


class BootError(Exception):
    """Startup cannot continue; the process exits non-zero."""


def verify_database(settings: Settings) -> None:
    """Open the pool, run ``SELECT 1`` and require a recorded ``schema.version``. Performs no DDL."""
    hint = "run `python -m api.db.init_db` first"
    try:
        init_database(settings.mysql)
        with DB.connection_context():
            DB.execute_sql("SELECT 1")
            version = current_version()
    except (peewee.PeeweeException, pymysql.MySQLError) as exc:
        raise BootError(f"database is not ready ({type(exc).__name__}); {hint}") from exc
    if version < 1:
        raise BootError(f"database has no schema.version; {hint}")


def build_executor(settings: Settings) -> tuple[Executor, RollUpDaemon, threading.Event]:
    queue = get_queue(settings)
    limiters = Limiters.from_settings(settings.ingest)
    deps = PipelineDeps(settings, get_storage(settings), get_doc_store(settings), EmbedRunner(settings, limiters), limiters)
    stop = threading.Event()
    return Executor(settings, queue, deps), RollUpDaemon(settings, queue, stop), stop


def main() -> int:
    try:
        settings = get_settings()
    except ConfigError as exc:
        init_root_logger(SERVICE_NAME)
        logger.error("configuration error: %s", exc)
        return 1
    init_root_logger(SERVICE_NAME, None, settings.logging.level)
    for noisy in QUIET_LOGGERS:  # transport debug logs can carry request headers
        logging.getLogger(noisy).setLevel(logging.WARNING)
    try:
        verify_database(settings)
        executor, daemon, daemon_stop = build_executor(settings)
        executor.queue.ping()
        executor.queue.ensure_group()
    except (BootError, QueueUnavailable) as exc:
        logger.error("boot failed: %s", exc)
        return 1

    def on_signal(signum: int, _frame: FrameType | None) -> None:
        logger.info("stop requested", extra={"signal": signum})
        executor.request_stop()
        daemon_stop.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, on_signal)
    logger.info("executor started", extra={"consumer": executor.name})
    daemon.start()
    try:
        executor.run_forever()
    finally:
        daemon_stop.set()
        daemon.join(10)
        with contextlib.suppress(Exception):
            executor.deps.embedder.close()
        reset_queue_cache()
        with contextlib.suppress(Exception):
            DB.close()
    logger.info("executor stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
