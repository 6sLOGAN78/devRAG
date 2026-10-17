"""Compose control of the task-executor service for the crash, poison and scaling tests (plan 04-22).

Only containers of the compose project (label ``com.docker.compose.project``) are ever touched. The fast-timing override makes lock, reclaim and
progress intervals short enough for a test; the default executor is restored by ``restore_default_executor`` (called in fixture teardown).
Waiting is polling with deadlines through ``wait_until``.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from contextlib import contextmanager

import valkey

from common.settings import Settings
from test.conftest import REPO_ROOT
from test.helpers.wait import wait_until
from test.testcases.conftest import COMPOSE_BASE, DOCKER, PROJECT

SERVICE = "task-executor"
OVERRIDE = "docker/docker-compose.executor-test.yml"


def _run(args: list[str], timeout: float = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False, timeout=timeout, cwd=REPO_ROOT)  # noqa: S603


def _compose(*args: str, override: bool = False, timeout: float = 300) -> subprocess.CompletedProcess[str]:
    files = ["-f", OVERRIDE] if override else []
    return _run([*COMPOSE_BASE, *files, *args], timeout)


def container_ids(*, all_states: bool = False) -> list[str]:
    """Ids of the project's task-executor containers (running ones unless ``all_states``)."""
    flag = "-aq" if all_states else "-q"
    out = _run(
        [DOCKER, "ps", flag, "--filter", f"label=com.docker.compose.project={PROJECT}", "--filter", f"label=com.docker.compose.service={SERVICE}"], 60
    )
    return out.stdout.split()


def inspect(container: str, fmt: str) -> str:
    return _run([DOCKER, "inspect", "--format", fmt, container], 60).stdout.strip()


def is_healthy(container: str) -> bool:
    return inspect(container, "{{.State.Health.Status}}") == "healthy"


def _all_healthy(count: int) -> list[str] | None:
    ids = container_ids()
    if len(ids) == count and all(is_healthy(c) for c in ids):
        return ids
    return None


def _recreate(count: int, *, override: bool) -> list[str]:
    result = _compose("up", "-d", "--no-deps", "--force-recreate", "--scale", f"{SERVICE}={count}", SERVICE, override=override)
    assert result.returncode == 0, result.stderr[-400:]
    ids = wait_until(lambda: _all_healthy(count), timeout=180, interval=2, describe=lambda: f"{count} healthy {SERVICE} containers never appeared")
    return list(ids)


def use_fast_executors(count: int) -> list[str]:
    """Recreate the executor service with the short-timing override at ``count`` replicas; returns the healthy container ids."""
    return _recreate(count, override=True)


def restore_default_executor() -> str:
    """Recreate the executor with the default compose files at one replica (no override environment); returns its id."""
    (cid,) = _recreate(1, override=False)
    env = inspect(cid, "{{range .Config.Env}}{{println .}}{{end}}")
    assert "INGEST_BATCH_SIZE=2" not in env.splitlines(), "the override environment survived the restore"
    assert not [c for c in container_ids(all_states=True) if c != cid and inspect(c, "{{.State.Status}}") != "running"], "a stopped executor was left behind"
    return cid


@contextmanager
def fast_executors(count: int) -> Iterator[list[str]]:
    """Fast-timing executors for the body; the default single executor is restored afterwards, whatever happened."""
    try:
        yield use_fast_executors(count)
    finally:
        restore_default_executor()


def stream_client(settings: Settings) -> valkey.Valkey:
    rd = settings.redis
    return valkey.Valkey(host=rd.host, port=rd.port, password=rd.password or None, db=rd.db, socket_timeout=5, socket_connect_timeout=5, decode_responses=True)


def stream_name(settings: Settings) -> str:
    return f"{settings.ingest.queue_prefix}.0.common"


def pending_entries(settings: Settings) -> list[dict]:
    client = stream_client(settings)
    try:
        return list(client.xpending_range(stream_name(settings), settings.ingest.consumer_group, "-", "+", 1000))
    except valkey.ResponseError:
        return []
    finally:
        client.close()


def pending_owner(settings: Settings) -> str:
    """Consumer name holding the oldest pending entry of the default stream ('' when nothing is pending)."""
    entries = pending_entries(settings)
    return str(entries[0]["consumer"]) if entries else ""


def consumers(settings: Settings) -> list[dict]:
    client = stream_client(settings)
    try:
        return [c for c in client.xinfo_consumers(stream_name(settings), settings.ingest.consumer_group) if str(c["name"]).startswith("te_")]
    except valkey.ResponseError:
        return []
    finally:
        client.close()


def container_of(consumer_name: str) -> str:
    """Running executor container whose id starts with the hostname part of ``te_{hostname}_{pid}_{rand}``; '' when none."""
    parts = consumer_name.split("_")
    if len(parts) < 4 or not consumer_name:
        return ""
    host = "_".join(parts[1:-2])
    matches = [c for c in container_ids() if c.startswith(host)]
    return matches[0] if len(matches) == 1 else ""


def kill(container: str) -> None:
    result = _run([DOCKER, "kill", container], 60)
    assert result.returncode == 0, result.stderr[-200:]


def stop(container: str, grace: int = 30) -> int:
    """``docker stop`` (SIGTERM, then SIGKILL after ``grace`` seconds); returns the container's exit code."""
    result = _run([DOCKER, "stop", "-t", str(grace), container], grace + 60)
    assert result.returncode == 0, result.stderr[-200:]
    return int(inspect(container, "{{.State.ExitCode}}"))


def logs_since(container: str, since_epoch: float) -> str:
    out = _run([DOCKER, "logs", "--since", str(int(since_epoch)), container], 60)
    return out.stdout + out.stderr
