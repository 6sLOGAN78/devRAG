"""Alive file for the container health probe (plan 04-12).

The executor loop and every task watcher touch ``ALIVE_FILE``; the probe (``python -m rag.svr.healthcheck``) exits 0 while the file is younger than
``ingest.worker_heartbeat_timeout`` seconds and 1 otherwise.
"""

from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)

ALIVE_FILE = Path(tempfile.gettempdir()) / "devrag-executor.alive"


def touch_alive(path: Path | None = None) -> None:
    target = path if path is not None else ALIVE_FILE
    try:
        target.touch(exist_ok=True)
    except OSError as exc:
        logger.warning("alive file not written", extra={"error_type": type(exc).__name__})


def is_alive(path: Path, max_age_seconds: float) -> bool:
    try:
        return time.time() - path.stat().st_mtime <= max_age_seconds
    except OSError:
        return False


def main() -> int:
    from common.settings import get_settings

    return 0 if is_alive(ALIVE_FILE, get_settings().ingest.worker_heartbeat_timeout) else 1


if __name__ == "__main__":
    raise SystemExit(main())
