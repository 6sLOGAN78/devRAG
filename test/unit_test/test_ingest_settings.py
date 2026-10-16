from __future__ import annotations

import pytest
import yaml

from common.settings import ConfigError, IngestSettings, load_settings
from scripts.render_conf import render
from test.conftest import REPO_ROOT

pytestmark = pytest.mark.unit

FAKE_KEY = "fake-test-secret-key-0123456789abcdef-ZZ"
SECRETS = {"MYSQL_PASSWORD": "pw-mysql-123", "REDIS_PASSWORD": "pw-redis-123", "MINIO_PASSWORD": "pw-minio-123", "ELASTIC_PASSWORD": "pw-es-123", "SECRET_KEY": FAKE_KEY}


def _render(tmp_path, extra=None):
    env = {**SECRETS, **(extra or {})}
    text = render((REPO_ROOT / "conf/service_conf.yaml.template").read_text(), env)
    path = tmp_path / "service_conf.yaml"
    path.write_text(text)
    return path


def _with(tmp_path, mutate):
    data = yaml.safe_load(_render(tmp_path).read_text())
    mutate(data)
    path = tmp_path / "m.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def test_defaults():
    i = IngestSettings()
    assert (i.task_page_size, i.batch_size, i.max_attempts) == (12, 64, 3)
    assert (i.lock_ttl_seconds, i.reclaim_idle_ms, i.reclaim_interval_seconds) == (60, 120000, 15)
    assert (i.worker_heartbeat_timeout, i.progress_interval_seconds, i.cancel_poll_seconds) == (120, 2, 1)
    assert (i.retry_backoff_max_seconds, i.reconcile_after_seconds) == (30, 300)
    assert (i.xlsx_max_cells, i.text_preview_chars) == (1000000, 262144)
    assert (i.parse_rate_max, i.parse_rate_window_seconds) == (120, 60)
    assert (i.queue_prefix, i.consumer_group) == ("te", "ragflow_consumer_group")
    assert (i.task_concurrency, i.chunk_concurrency, i.embed_concurrency) == (1, 1, 2)
    assert (i.storage_concurrency, i.kg_concurrency, i.pdf_render_threads) == (4, 1, 2)


def test_rendered_template_matches_defaults(tmp_path):
    assert load_settings(_render(tmp_path)).ingest == IngestSettings()


def test_env_flows_into_max_attempts(tmp_path):
    assert load_settings(_render(tmp_path, {"INGEST_MAX_ATTEMPTS": "5"})).ingest.max_attempts == 5


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("task_page_size", 0), ("task_page_size", 1001), ("batch_size", 0), ("batch_size", 257),
        ("max_attempts", 0), ("max_attempts", 11), ("lock_ttl_seconds", 4), ("lock_ttl_seconds", 601),
        ("cancel_poll_seconds", 0), ("pdf_render_threads", 9),
    ],
)
def test_out_of_range_rejected_without_echo(tmp_path, key, value):
    path = _with(tmp_path, lambda d: d["ingest"].__setitem__(key, value))
    with pytest.raises(ConfigError) as err:
        load_settings(path)
    assert f"ingest.{key}" in str(err.value)
    assert str(value) not in str(err.value).replace(f"ingest.{key}", "")


def test_reclaim_idle_below_twice_lock_ttl_rejected(tmp_path):
    def mutate(d):
        d["ingest"]["lock_ttl_seconds"] = 60
        d["ingest"]["reclaim_idle_ms"] = 119999

    with pytest.raises(ConfigError, match=r"ingest\.reclaim_idle_ms"):
        load_settings(_with(tmp_path, mutate))


@pytest.mark.parametrize("key", ["queue_prefix", "consumer_group"])
@pytest.mark.parametrize("bad", ["Has Space", "a*b", "x" * 33, "UPPER"])
def test_bad_names_rejected(tmp_path, key, bad):
    path = _with(tmp_path, lambda d: d["ingest"].__setitem__(key, bad))
    with pytest.raises(ConfigError, match=rf"ingest\.{key}"):
        load_settings(path)
