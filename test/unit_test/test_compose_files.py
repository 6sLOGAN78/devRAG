"""Static pins for the task-executor compose service, its dev and test overrides and the Valkey policy (04-13)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.unit

DOCKER = Path(__file__).resolve().parents[2] / "docker"


def _load(name: str) -> dict[str, Any]:
    return yaml.safe_load((DOCKER / name).read_text(encoding="utf-8"))


def test_task_executor_service_shape() -> None:
    svc = _load("docker-compose.yml")["services"]["task-executor"]
    assert svc["profiles"] == ["cpu"]
    assert svc["restart"] == "unless-stopped"
    assert svc["image"] == "${RAGFLOW_IMAGE:-devrag-app:local}"
    assert svc["pull_policy"] == "never"
    for forbidden in ("build", "container_name", "ports"):
        assert forbidden not in svc
    assert svc["entrypoint"] == ["tini", "--", "/ragflow/docker/entrypoint_task_executor.sh"]
    assert svc["healthcheck"]["test"] == ["CMD", "/ragflow/docker/healthcheck_task_executor.sh"]
    assert svc["depends_on"]["init"]["condition"] == "service_completed_successfully"
    assert svc["networks"] == ["ragflow"]
    assert "APP_UID" in svc["environment"]
    assert "MYSQL_PASSWORD" in svc["environment"]


def test_dev_override_carries_the_dev_only_settings() -> None:
    svc = _load("docker-compose.dev.yml")["services"]["task-executor"]
    assert svc["mem_limit"] == "384m"
    assert "host.docker.internal:host-gateway" in svc["extra_hosts"]
    assert "LLM_ALLOW_PRIVATE_BASE_URLS" in svc["environment"]


def test_production_file_has_no_dev_settings_in_the_executor_block() -> None:
    svc = _load("docker-compose.yml")["services"]["task-executor"]
    assert "mem_limit" not in svc
    assert "extra_hosts" not in svc
    # LLM_ALLOW_PRIVATE_BASE_URLS reaches the service only through the shared x-app-env default (false).
    assert set(svc["environment"]) - {"APP_UID", "APP_GID"} == set(_load("docker-compose.yml")["services"]["app"]["environment"]) - {"APP_UID", "APP_GID"}
    assert svc["environment"]["LLM_ALLOW_PRIVATE_BASE_URLS"] == "${LLM_ALLOW_PRIVATE_BASE_URLS:-false}"


def test_executor_test_override_only_touches_the_executor() -> None:
    doc = _load("docker-compose.executor-test.yml")
    assert list(doc["services"]) == ["task-executor"]
    env = doc["services"]["task-executor"]["environment"]
    assert env == {
        "INGEST_BATCH_SIZE": "2",
        "TASK_LOCK_TTL_SECONDS": "8",
        "RECLAIM_IDLE_MS": "16000",
        "RECLAIM_INTERVAL_SECONDS": "3",
        "CANCEL_POLL_SECONDS": "1",
        "PROGRESS_INTERVAL_SECONDS": "1",
        "INGEST_RETRY_BACKOFF_MAX_SECONDS": "2",
    }


def test_valkey_keeps_stream_entries() -> None:
    text = (DOCKER / "docker-compose-base.yml").read_text(encoding="utf-8")
    assert text.count("volatile-lru") == 1
    assert "allkeys-lru" not in text
    assert "allkeys-lru" not in (DOCKER / "docker-compose.dev.yml").read_text(encoding="utf-8")
