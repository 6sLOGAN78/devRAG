"""The env catalog covers the documented variables and secrets are fail-fast (DEPLOY-11, SEC-04)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "docker" / ".env.example"
BASE = ROOT / "docker" / "docker-compose-base.yml"
DOC = ROOT / "docs" / "18-deployment" / "environment-variables.md"


def parse_env(path: Path) -> tuple[dict[str, str], set[str]]:
    values: dict[str, str] = {}
    secrets: set[str] = set()
    marker = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line == "# secret":
            marker = True
            continue
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key] = value
            if marker:
                secrets.add(key)
        if line:
            marker = False
    return values, secrets


def test_every_documented_variable_is_in_the_example() -> None:
    if not DOC.is_file():
        pytest.skip("docs/ is untracked and absent in this checkout")
    documented = set(re.findall(r"^\| `([A-Z][A-Z0-9_]+)` \|", DOC.read_text(encoding="utf-8"), flags=re.M))
    assert len(documented) > 20
    values, _ = parse_env(EXAMPLE)
    missing = sorted(documented - set(values))
    assert not missing, f"documented variables missing from docker/.env.example: {missing}"


def test_secrets_are_empty_in_the_example() -> None:
    values, secrets = parse_env(EXAMPLE)
    required = {"MYSQL_ROOT_PASSWORD", "MYSQL_PASSWORD", "REDIS_PASSWORD", "MINIO_PASSWORD", "ELASTIC_PASSWORD"}
    assert required <= secrets
    for key in secrets:
        assert values[key] == "", f"{key} must be empty in the example"


def compose_config(env_file: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "--env-file", str(env_file), "-f", str(BASE), "--profile", "elasticsearch", "config", "-q"],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )


def test_compose_fails_fast_when_a_secret_is_unset() -> None:
    result = compose_config(EXAMPLE)
    assert result.returncode != 0
    assert re.search(r"(MYSQL_ROOT_PASSWORD|MYSQL_PASSWORD|REDIS_PASSWORD|MINIO_PASSWORD|ELASTIC_PASSWORD) is unset", result.stderr)


def test_compose_accepts_supplied_secrets(tmp_path: Path) -> None:
    lines = []
    values, secrets = parse_env(EXAMPLE)
    for key, value in values.items():
        lines.append(f"{key}={'dummy-value' if key in secrets else value}")
    env_file = tmp_path / "test.env"
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = compose_config(env_file)
    assert result.returncode == 0, result.stderr


NEW_VARIABLES = {
    "SECRET_KEY", "REGISTER_ENABLED", "SUPERUSER_EMAIL", "SUPERUSER_PASSWORD", "OTP_TTL_SECONDS",
    "SMTP_HOST", "SMTP_PORT", "SMTP_SECURITY", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM",
    "DEFAULT_CHAT_MODEL", "DEFAULT_EMBEDDING_MODEL", "DEFAULT_RERANK_MODEL", "DEFAULT_MODEL_FACTORY", "DEFAULT_MODEL_BASE_URL",
    "RATE_LIMIT_REGISTER_PER_IP", "RATE_LIMIT_REGISTER_WINDOW_SECONDS", "RATE_LIMIT_LOGIN_FAILURES_PER_EMAIL",
    "RATE_LIMIT_LOGIN_PER_IP", "RATE_LIMIT_LOGIN_WINDOW_SECONDS", "RATE_LIMIT_OTP_EMAIL_INTERVAL_SECONDS",
    "RATE_LIMIT_OTP_PER_EMAIL_PER_HOUR", "RATE_LIMIT_OTP_PER_IP_PER_HOUR", "RATE_LIMIT_OTP_WINDOW_SECONDS",
}


def test_phase2_variables_are_catalogued_and_secrets_empty() -> None:
    values, secrets = parse_env(EXAMPLE)
    assert NEW_VARIABLES <= set(values), sorted(NEW_VARIABLES - set(values))
    assert {"SECRET_KEY", "SMTP_PASSWORD", "SUPERUSER_PASSWORD"} <= secrets
    for key in ("SECRET_KEY", "SMTP_PASSWORD", "SUPERUSER_PASSWORD", "SUPERUSER_EMAIL"):
        assert values[key] == ""
    assert values["REGISTER_ENABLED"] == "1"
    assert values["OTP_TTL_SECONDS"] == "600"


def test_dev_rate_limit_override_is_documented_but_not_set_in_the_example() -> None:
    values, _ = parse_env(EXAMPLE)
    assert "DEV_RATE_LIMIT_PER_IP_MAX" not in values
    assert "# DEV_RATE_LIMIT_PER_IP_MAX" in EXAMPLE.read_text(encoding="utf-8")


PHASE3_VARIABLES = {
    "LLM_KEY_ENCRYPTION_KEY", "LLM_KEY_ID", "LLM_ALLOW_PRIVATE_BASE_URLS", "LLM_CHAT_TIMEOUT_SECONDS",
    "LLM_EMBEDDING_TIMEOUT_SECONDS", "LLM_KEY_TEST_TIMEOUT_SECONDS", "LLM_MAX_RETRIES",
    "RATE_LIMIT_PROVIDER_TEST_PER_TENANT", "RATE_LIMIT_PROVIDER_TEST_WINDOW_SECONDS",
    "STORAGE_IMPL", "STORAGE_LOCAL_DIR", "UPLOAD_MAX_FILE_BYTES", "UPLOAD_MAX_FILES_PER_REQUEST",
    "DATASET_MAX_DOCUMENTS", "UPLOAD_BODY_TIMEOUT_SECONDS", "UPLOAD_ALLOWED_EXTENSIONS",
    "OPENROUTER_API_KEY", "LIVE_CHAT_MODEL", "LIVE_EMBED_MODEL", "LIVE_EXPECTED_DIM",
}
NOT_IN_CONTAINER = {"OPENROUTER_API_KEY", "LIVE_CHAT_MODEL", "LIVE_EMBED_MODEL", "LIVE_EXPECTED_DIM"}


def test_phase3_variables_are_catalogued_and_secrets_empty() -> None:
    values, secrets = parse_env(EXAMPLE)
    assert PHASE3_VARIABLES <= set(values), sorted(PHASE3_VARIABLES - set(values))
    assert {"LLM_KEY_ENCRYPTION_KEY", "OPENROUTER_API_KEY"} <= secrets
    assert values["LLM_KEY_ENCRYPTION_KEY"] == "" and values["OPENROUTER_API_KEY"] == ""
    assert values["UPLOAD_MAX_FILE_BYTES"] == "104857600"
    assert values["UPLOAD_MAX_FILES_PER_REQUEST"] == "20"
    assert values["DATASET_MAX_DOCUMENTS"] == "10000"
    assert values["LIVE_EXPECTED_DIM"] == "1024"
    assert values["LLM_ALLOW_PRIVATE_BASE_URLS"] in ("0", "false")


def test_phase3_non_secret_live_variables_are_not_marked_secret() -> None:
    _, secrets = parse_env(EXAMPLE)
    assert not ({"LIVE_CHAT_MODEL", "LIVE_EMBED_MODEL", "LIVE_EXPECTED_DIM"} & secrets)


def test_compose_passes_phase3_variables_but_never_the_live_key() -> None:
    text = (ROOT / "docker" / "docker-compose.yml").read_text(encoding="utf-8")
    for name in sorted(PHASE3_VARIABLES - NOT_IN_CONTAINER):
        assert f"  {name}:" in text, f"{name} is not passed to the app service"
    for name in sorted(NOT_IN_CONTAINER):
        assert name not in text, f"{name} must not reach the container"
    assert "LLM_KEY_ENCRYPTION_KEY: ${LLM_KEY_ENCRYPTION_KEY:?" in text


PHASE4_VARIABLES = (
    "TASK_PAGE_SIZE",
    "INGEST_BATCH_SIZE",
    "INGEST_MAX_ATTEMPTS",
    "TASK_LOCK_TTL_SECONDS",
    "RECLAIM_IDLE_MS",
    "RECLAIM_INTERVAL_SECONDS",
    "WORKER_HEARTBEAT_TIMEOUT",
    "PROGRESS_INTERVAL_SECONDS",
    "CANCEL_POLL_SECONDS",
    "INGEST_RETRY_BACKOFF_MAX_SECONDS",
    "RECONCILE_AFTER_SECONDS",
    "XLSX_MAX_CELLS",
    "TEXT_PREVIEW_CHARS",
    "PARSE_RATE_MAX",
    "PARSE_RATE_WINDOW_SECONDS",
    "INGEST_TASK_CONCURRENCY",
    "INGEST_CHUNK_CONCURRENCY",
    "INGEST_EMBED_CONCURRENCY",
    "INGEST_STORAGE_CONCURRENCY",
    "INGEST_KG_CONCURRENCY",
    "PDF_RENDER_THREADS",
    "INGEST_QUEUE_PREFIX",
    "INGEST_CONSUMER_GROUP",
)


def test_phase4_variables_are_catalogued_and_passed_to_the_app() -> None:
    values, secrets = parse_env(EXAMPLE)
    assert set(PHASE4_VARIABLES) <= set(values), sorted(set(PHASE4_VARIABLES) - set(values))
    assert not (set(PHASE4_VARIABLES) & secrets)
    assert values["INGEST_MAX_ATTEMPTS"] == "3"
    text = (ROOT / "docker" / "docker-compose.yml").read_text(encoding="utf-8")
    for name in PHASE4_VARIABLES:
        assert f"  {name}:" in text, f"{name} is not passed to the app service"


PHASE5_RETRIEVAL_VARIABLES = {
    "RETRIEVAL_TOP_K": "1024",
    "RETRIEVAL_RERANK_MAX_CANDIDATES": "64",
    "RETRIEVAL_MSM_PERCENT": "30",
    "RETRIEVAL_MSM_RETRY_PERCENT": "10",
    "RETRIEVAL_SYNONYM_TTL_SECONDS": "86400",
    "RETRIEVAL_RATE_MAX": "30",
    "RETRIEVAL_RATE_WINDOW_SECONDS": "60",
}


def test_retrieval_variables_are_catalogued_with_defaults_and_passed_to_the_app() -> None:
    values, secrets = parse_env(EXAMPLE)
    for name, default in PHASE5_RETRIEVAL_VARIABLES.items():
        assert values.get(name) == default, name
    assert not (set(PHASE5_RETRIEVAL_VARIABLES) & secrets)
    compose = (ROOT / "docker" / "docker-compose.yml").read_text(encoding="utf-8")
    template = (ROOT / "conf" / "service_conf.yaml.template").read_text(encoding="utf-8")
    for name in PHASE5_RETRIEVAL_VARIABLES:
        assert f"  {name}:" in compose, f"{name} is not passed to the app service"
        assert "${" + name + ":-" in template, f"{name} is not read by the template"
