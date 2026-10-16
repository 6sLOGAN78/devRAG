"""The per-tenant parse request limit (plan 04-14; D-19, T-04-14-03).

Runs against the real Valkey. Every key is made unique per test and removed by its exact name.
"""

from __future__ import annotations

import dataclasses
import secrets
from collections.abc import Iterator

import pytest
import valkey

from api.db.services import ingestion_service as ing
from api.db.services.service_errors import Kind, ServiceError
from common.settings import Settings, load_settings

pytestmark = pytest.mark.integration


def _key(tenant_id: str) -> str:
    return f"parse:{tenant_id}"


def _with_limit(maximum: int) -> Settings:
    cfg = load_settings()
    return dataclasses.replace(cfg, ingest=dataclasses.replace(cfg.ingest, parse_rate_max=maximum, parse_rate_window_seconds=60))


@pytest.fixture
def tenants() -> Iterator[tuple[Settings, str, str]]:
    cfg = _with_limit(3)
    first, second = f"t{secrets.token_hex(8)}", f"t{secrets.token_hex(8)}"
    yield cfg, first, second
    rd = cfg.redis
    raw = valkey.Valkey(host=rd.host, port=rd.port, password=rd.password or None, db=rd.db)
    try:
        raw.delete(_key(first), _key(second))
    finally:
        raw.close()


def test_the_fourth_request_in_a_window_is_rate_limited_and_another_tenant_is_not(tenants) -> None:
    cfg, first, second = tenants
    for _ in range(3):
        ing.parse_rate_guard(cfg, first)
    with pytest.raises(ServiceError) as caught:
        ing.parse_rate_guard(cfg, first)
    assert caught.value.kind is Kind.RATE_LIMITED and caught.value.retry_after is not None and caught.value.retry_after > 0
    ing.parse_rate_guard(cfg, second)


def test_an_unreachable_store_refuses_instead_of_allowing(tenants) -> None:
    cfg, first, _ = tenants
    closed = dataclasses.replace(cfg, redis=dataclasses.replace(cfg.redis, host="127.0.0.1", port=1))
    with pytest.raises(ServiceError) as caught:
        ing.parse_rate_guard(closed, first)
    assert caught.value.kind is Kind.UNAVAILABLE and caught.value.reason == "queue_unavailable"
