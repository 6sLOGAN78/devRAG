"""The task-executor container of the running `devrag-stack` project (needs `make up`; plan 04-13)."""
from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterator

import pytest
import valkey

from test.conftest import REPO_ROOT, stack_env
from test.helpers.wait import wait_until

pytestmark = pytest.mark.integration

ENV = stack_env()
PROJECT = ENV.get("COMPOSE_PROJECT_NAME", "devrag-stack")
COMPOSE_FILES = ["-f", "docker/docker-compose.yml", "-f", "docker/docker-compose.dev.yml"]
DOCKER = shutil.which("docker") or "docker"
SERVICE = "task-executor"
STREAM = "te.0.common"
GROUP = "ragflow_consumer_group"


def _run(args: list[str], timeout: float = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False, timeout=timeout, cwd=REPO_ROOT)  # noqa: S603


def _compose(*args: str, timeout: float = 300) -> subprocess.CompletedProcess[str]:
    return _run([DOCKER, "compose", "-p", PROJECT, "--env-file", "docker/.env", *COMPOSE_FILES, "--profile", "cpu", *args], timeout)


def _ids() -> list[str]:
    return _run([DOCKER, "ps", "-q", "--filter", f"label=com.docker.compose.project={PROJECT}",
                 "--filter", f"label=com.docker.compose.service={SERVICE}"]).stdout.split()


def _inspect(cid: str, fmt: str) -> str:
    return _run([DOCKER, "inspect", "--format", fmt, cid]).stdout.strip()


def _healthy(cid: str) -> bool:
    return _inspect(cid, "{{.State.Health.Status}}") == "healthy"


def _client() -> valkey.Valkey:
    return valkey.Valkey(host="127.0.0.1", port=int(ENV.get("REDIS_PORT", "6380")), password=ENV.get("REDIS_PASSWORD"), db=int(ENV.get("REDIS_DB", "1")), decode_responses=True, socket_timeout=5)


def _consumers() -> list[str]:
    try:
        return [c["name"] for c in _client().xinfo_consumers(STREAM, GROUP) if c["name"].startswith("te_")]
    except valkey.ResponseError:
        return []


def _only_one() -> str:
    ids = wait_until(_ids, timeout=60, interval=1)
    assert len(ids) == 1
    return ids[0]


def test_container_runs_and_becomes_healthy() -> None:
    cid = _only_one()
    assert _inspect(cid, "{{.State.Status}}") == "running"
    assert wait_until(lambda: _healthy(cid), timeout=120, interval=2)


def test_logs_show_start_and_no_secrets() -> None:
    cid = _only_one()
    wait_until(lambda: _healthy(cid), timeout=120, interval=2)
    logs = _run([DOCKER, "logs", cid])
    text = logs.stdout + logs.stderr
    assert text.strip()
    assert "Traceback" not in text
    assert "password" not in text.lower()
    for key in ("REDIS_PASSWORD", "MYSQL_PASSWORD", "MYSQL_ROOT_PASSWORD", "MINIO_PASSWORD", "ELASTIC_PASSWORD"):
        value = ENV.get(key)
        if value:
            assert value not in text, f"{key} value appears in the executor log"


def test_executor_registers_a_consumer() -> None:
    _only_one()
    assert wait_until(_consumers, timeout=60, interval=1)


def test_valkey_keeps_stream_entries() -> None:
    assert _client().config_get("maxmemory-policy")["maxmemory-policy"] == "volatile-lru"


def test_memory_limit_and_unprivileged_process() -> None:
    cid = _only_one()
    assert _inspect(cid, "{{.HostConfig.Memory}}") == str(384 * 1024 * 1024), "dev cap set in 04-35 from the measured peak (R-188)"
    # `docker exec` starts as root; the executor process itself must be the unprivileged one (setpriv in the entrypoint).
    lines = _run([DOCKER, "top", cid]).stdout.splitlines()[1:]
    users = [line.split(None, 7) for line in lines]
    executor = [cols[0] for cols in users if len(cols) > 7 and "rag.svr.task_executor" in cols[7]]
    assert executor, lines
    assert all(user != "root" and user != "0" for user in executor), lines


@pytest.fixture
def restore_single() -> Iterator[None]:
    yield
    _compose("up", "-d", "--no-recreate", "--scale", f"{SERVICE}=1", SERVICE)
    # --no-recreate does not remove the extra replica on every compose version; make sure exactly one is left.
    ids = _ids()
    for extra in ids[1:]:
        _run([DOCKER, "rm", "-f", extra])


def test_scales_to_two_without_configuration(restore_single: None) -> None:
    first = _only_one()
    wait_until(lambda: _healthy(first), timeout=120, interval=2)
    before = set(_consumers())
    result = _compose("up", "-d", "--no-recreate", "--scale", f"{SERVICE}=2", SERVICE)
    assert result.returncode == 0, result.stderr
    ids = wait_until(lambda: len(_ids()) == 2 and _ids(), timeout=60, interval=1)
    assert len(ids) == 2
    for cid in ids:
        assert wait_until(lambda cid=cid: _healthy(cid), timeout=120, interval=2)
    names = wait_until(lambda: len(set(_consumers()) - before) >= 1 and set(_consumers()), timeout=60, interval=1)
    assert len(names) >= 2


def test_graceful_stop_exits_zero_and_container_comes_back() -> None:
    cid = _only_one()
    wait_until(lambda: _healthy(cid), timeout=120, interval=2)
    result = _run([DOCKER, "stop", "-t", "30", cid])
    assert result.returncode == 0, result.stderr
    assert _inspect(cid, "{{.State.ExitCode}}") == "0"
    try:
        # A manual stop is not restarted by `unless-stopped`; bring it back through compose.
        _compose("up", "-d", SERVICE)
        ids = wait_until(_ids, timeout=60, interval=1)
        assert wait_until(lambda: _healthy(ids[0]), timeout=120, interval=2)
    finally:
        _compose("up", "-d", SERVICE)
