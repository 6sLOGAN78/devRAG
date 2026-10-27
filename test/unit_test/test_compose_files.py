"""Static pins for the task-executor compose service, its dev and test overrides and the Valkey policy (04-13)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.unit

DOCKER = Path(__file__).resolve().parents[2] / "docker"


def test_deepdoc_profile_has_isolated_production_boundary_and_bounded_dev_probe():
    document = _load("docker-compose.yml")
    service = document["services"]["deepdoc"]
    assert service["profiles"] == ["deepdoc"]
    assert service["user"] == "10001:10001" and service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert service["security_opt"] == ["no-new-privileges:true"]
    assert service["networks"] == ["deepdoc"]
    assert document["networks"]["deepdoc"]["internal"] is True
    assert "ports" not in service and "MYSQL_PASSWORD" not in service["environment"]
    assert "DEEPDOC_API_TOKEN" in service["environment"]
    dev = _load("docker-compose.dev.yml")["services"]["deepdoc"]
    assert dev["mem_limit"] == "3g" and dev["cpus"] == 2
    assert dev["ports"] == ["127.0.0.1:${DEEPDOC_PORT:-9390}:9390"]


def test_operator_native_entry_and_full_gate_enable_deepdoc_explicitly():
    root = DOCKER.parent
    assert "deepdoc-up:" in (root / "Makefile").read_text()
    assert "--profile deepdoc" in (root / "Makefile").read_text()
    assert "CLEAN_ROOM_DEEPDOC" in (root / "scripts/clean_room.sh").read_text()
    assert "DEEPDOC_API_TOKEN" in (root / "scripts/preflight.sh").read_text()


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
    assert svc["networks"] == ["ragflow", "deepdoc"]
    app = _load("docker-compose.yml")["services"]["app"]
    assert set(app["networks"]) == {"ragflow", "deepdoc"}
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


def test_tei_service_uses_the_approved_image_and_persistent_model_cache() -> None:
    base = _load("docker-compose-base.yml")
    svc = base["services"]["tei"]
    assert svc["profiles"] == ["tei-cpu"]
    assert svc["image"] == "${TEI_IMAGE:-ghcr.io/huggingface/text-embeddings-inference:cpu-1.9.4}"
    assert svc["command"] == ["--model-id", "${TEI_RERANK_MODEL:-BAAI/bge-reranker-base}", "--auto-truncate"]
    assert svc["ports"] == ["${BIND_HOST:-127.0.0.1}:${TEI_PORT:-6381}:80"]
    assert svc["environment"]["REVISION"] == "${TEI_RERANK_REVISION:-2cfc18c9415c912f9d8155881c133215df768a70}"
    assert svc["volumes"] == ["tei_data:/data"]
    assert svc["networks"]["ragflow"]["aliases"] == ["tei"]
    assert svc["healthcheck"]["test"] == ["CMD", "curl", "-fsS", "http://localhost:80/health"]
    assert svc["healthcheck"]["start_period"] == "300s"
    assert "tei_data" in base["volumes"]
    assert "mem_limit" not in svc
    assert "mem_limit" not in _load("docker-compose.yml")["services"].get("tei", {})
    assert "mem_limit" in _load("docker-compose.dev.yml")["services"]["tei"]


def test_tei_is_wired_into_stack_entry_points() -> None:
    root = DOCKER.parent
    for name in ("Makefile", "scripts/clean_room.sh"):
        assert "--profile tei-cpu" in (root / name).read_text()
    assert "WAIT_STACK_TIMEOUT=900" in (root / "Makefile").read_text()
    assert "TEI requires at least 6 GB free" in (root / "scripts/preflight.sh").read_text()
