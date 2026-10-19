"""Rerank driver contract tests against the loopback fake provider (plan 05-05, LLM-09, RETR-11, D-01, D-02, T-05-05-01..03).

The fake provider is the third party's end of the wire (a TEI server and an OpenRouter rerank API); the drivers use their real HTTP client.
Backoff is injected, so no test waits.
"""
from __future__ import annotations

import asyncio
import logging

import pytest

from common.settings import LlmSettings
from rag.llm import Provider, resolve_provider
from rag.llm.errors import LLMErrorCode, ModelException
from rag.llm.rerank_model import OpenRouterRerank, RerankResult, TEIRerank, build_rerank, normalize_rank
from test.helpers.fake_provider import FAKE_KEY, SECRET_ECHO_KEY, fake_provider  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit

QUERY = "alpha beta"
TEXTS = ["beta only", "nothing here", "alpha beta together", "alpha alone"]


class Sleeps:
    """Injected backoff: records the delay and never waits."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


def make(provider, model, base, *, key=FAKE_KEY, retries=3, sleeps=None, allow_private=True, timeout=10.0):
    return build_rerank(
        resolve_provider(provider),
        model,
        key,
        base,
        None,
        llm_settings=LlmSettings(max_retries=retries),
        allow_private=allow_private,
        deny_hosts=(),
        sleep=sleeps if sleeps is not None else Sleeps(),
        timeout=timeout,
    )


def tei(fake, name=None, **kwargs):
    base = fake.root if name is None else f"{fake.root}/scripted/{name}"
    return make("TEI", "tei-model", base, key=None, **kwargs)


def openrouter(fake, model="rerank-model", name=None, **kwargs):
    base = f"{fake.root}/api/v1" if name is None else f"{fake.root}/scripted/{name}/api/v1"
    return make("OpenRouter", model, base, **kwargs)


def similarity(driver, query, texts):
    return asyncio.run(driver.similarity(query, texts))


def posts(fake, path):
    return [r for r in fake.requests if r.path == path]


# --- the factory ---------------------------------------------------------------------------------------------------
def test_build_rerank_picks_the_driver_by_provider(fake_provider):  # noqa: F811
    assert isinstance(tei(fake_provider), TEIRerank)
    assert isinstance(openrouter(fake_provider), OpenRouterRerank)


@pytest.mark.parametrize("provider", ["OpenAI", "Azure-OpenAI", "Ollama", "OpenAI-API-Compatible"])
def test_build_rerank_refuses_a_provider_without_a_rerank_driver(provider):
    with pytest.raises(ValueError):
        make(provider, "m", "http://127.0.0.1:1")


def test_construction_does_no_io(fake_provider):  # noqa: F811
    tei(fake_provider)
    openrouter(fake_provider)
    assert fake_provider.requests == []


# --- normalisation -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ([], []),
        ([0.0, 0.5, 1.0], [0.0, 0.5, 1.0]),  # already in range: unchanged
        ([0.2], [0.2]),
        ([-2.0, 0.0, 2.0], [0.0, 0.5, 1.0]),  # min-max
        ([5.0, 10.0], [0.0, 1.0]),
        ([7.0, 7.0004], [1.0, 1.0]),  # span below 1e-3: clip of the raw value
        ([-3.0, -3.0], [0.0, 0.0]),
        ([float("nan"), 0.4], [0.0, 0.4]),  # never NaN
    ],
)
def test_normalize_rank_table(raw, expected):
    assert normalize_rank(raw) == pytest.approx(expected)


def test_normalize_rank_never_leaves_the_unit_interval():
    out = normalize_rank([-1e9, 3.0, 1e9, float("inf"), float("-inf")])
    assert all(0.0 <= v <= 1.0 for v in out)


# --- TEI -----------------------------------------------------------------------------------------------------------
def test_tei_restores_the_input_order_by_index_and_scores_in_unit_range(fake_provider):  # noqa: F811
    result = similarity(tei(fake_provider), QUERY, TEXTS)
    assert isinstance(result, RerankResult)
    assert result.scores == pytest.approx([0.5, 0.0, 1.0, 0.5])  # the fake answers in score order; the driver puts each score back at its index
    assert all(0.0 <= s <= 1.0 for s in result.scores)
    assert result.tokens > 0 and result.estimated is True


def test_tei_request_shape(fake_provider):  # noqa: F811
    similarity(tei(fake_provider), QUERY, TEXTS)
    (call,) = posts(fake_provider, "/rerank")
    assert call.body == {"query": QUERY, "texts": TEXTS, "raw_scores": False, "truncate": True}
    assert "authorization" not in call.headers  # keyless instance sends no credential


def test_tei_sends_the_key_when_one_is_set(fake_provider):  # noqa: F811
    similarity(make("TEI", "m", fake_provider.root, key=FAKE_KEY), QUERY, TEXTS)
    assert posts(fake_provider, "/rerank")[0].headers["authorization"] == f"Bearer {FAKE_KEY}"


def test_tei_splits_seventy_texts_into_batches_of_32_32_6(fake_provider):  # noqa: F811
    texts = [f"alpha {i}" if i % 2 else f"beta {i}" for i in range(70)]
    result = similarity(tei(fake_provider), QUERY, texts)
    assert [len(r.body["texts"]) for r in posts(fake_provider, "/rerank")] == [32, 32, 6]
    assert len(result.scores) == 70
    assert result.scores[1] == pytest.approx(0.5) and result.scores[0] == pytest.approx(0.5)


def test_empty_query_or_texts_return_zeros_without_a_request(fake_provider):  # noqa: F811
    driver = tei(fake_provider)
    assert similarity(driver, "", ["a", "b"]).scores == [0.0, 0.0]
    assert similarity(driver, "   ", ["a"]).scores == [0.0]
    assert similarity(driver, QUERY, []).scores == []
    assert fake_provider.requests == []


# --- OpenRouter ----------------------------------------------------------------------------------------------------
def test_openrouter_request_shape_and_bearer_key(fake_provider):  # noqa: F811
    result = similarity(openrouter(fake_provider), QUERY, TEXTS)
    (call,) = posts(fake_provider, "/api/v1/rerank")
    assert call.body == {"model": "rerank-model", "query": QUERY, "documents": TEXTS, "top_n": len(TEXTS)}
    assert call.headers["authorization"] == f"Bearer {FAKE_KEY}"
    assert result.scores == pytest.approx([0.5, 0.0, 1.0, 0.5])


def test_openrouter_reads_usage_when_the_provider_sends_it(fake_provider):  # noqa: F811
    result = similarity(openrouter(fake_provider), QUERY, TEXTS)
    assert result.tokens == sum(len(t.split()) for t in TEXTS) and result.estimated is False


# --- errors --------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("name", "code", "retryable"),
    [
        ("fake-401", LLMErrorCode.ERROR_AUTHENTICATION, False),
        ("fake-402", LLMErrorCode.ERROR_QUOTA, False),
        ("fake-413", LLMErrorCode.ERROR_INVALID_REQUEST, False),
        ("fake-422", LLMErrorCode.ERROR_INVALID_REQUEST, False),
        ("fake-424", LLMErrorCode.ERROR_INVALID_REQUEST, False),
        ("fake-500", LLMErrorCode.ERROR_SERVER, False),
    ],
)
@pytest.mark.parametrize("kind", ["tei", "openrouter"])
def test_status_codes_map_to_typed_errors_without_a_retry(kind, name, code, retryable, fake_provider):  # noqa: F811
    sleeps = Sleeps()
    driver = tei(fake_provider, name, sleeps=sleeps) if kind == "tei" else openrouter(fake_provider, name=name, sleeps=sleeps)
    with pytest.raises(ModelException) as info:
        similarity(driver, QUERY, TEXTS)
    assert info.value.code == code and info.value.retryable is retryable
    assert sleeps.delays == []


@pytest.mark.parametrize("kind", ["tei", "openrouter"])
def test_a_rate_limit_is_retried_once_and_then_succeeds(kind, fake_provider):  # noqa: F811
    sleeps = Sleeps()
    driver = tei(fake_provider, "fake-429-once", sleeps=sleeps) if kind == "tei" else openrouter(fake_provider, name="fake-429-once", sleeps=sleeps)
    assert similarity(driver, QUERY, TEXTS).scores == pytest.approx([0.5, 0.0, 1.0, 0.5])
    assert len(sleeps.delays) == 1


def test_a_service_unavailable_answer_is_retryable(fake_provider):  # noqa: F811
    sleeps = Sleeps()
    with pytest.raises(ModelException) as info:
        similarity(tei(fake_provider, "fake-503", retries=2, sleeps=sleeps), QUERY, TEXTS)
    assert info.value.code == LLMErrorCode.ERROR_MAX_RETRIES and info.value.provider_status == 503
    assert len(sleeps.delays) == 2


def test_a_refused_connection_is_a_connection_error():
    with pytest.raises(ModelException) as info:
        similarity(make("TEI", "m", "http://127.0.0.1:1", key=None, retries=0), QUERY, TEXTS)
    assert info.value.code == LLMErrorCode.ERROR_CONNECTION


@pytest.mark.parametrize("kind", ["tei", "openrouter"])
def test_a_redirect_is_not_followed(kind, fake_provider):  # noqa: F811
    driver = tei(fake_provider, "fake-redirect") if kind == "tei" else openrouter(fake_provider, name="fake-redirect")
    with pytest.raises(ModelException):
        similarity(driver, QUERY, TEXTS)
    assert fake_provider.hits("/v1/redirect-target") == []


def test_a_missing_index_in_a_batch_is_an_invalid_response(fake_provider, monkeypatch):  # noqa: F811
    driver = tei(fake_provider)
    original = driver._parse

    def drop_one(payload, size):
        return original(payload[:-1] if isinstance(payload, list) else payload, size)

    monkeypatch.setattr(driver, "_parse", drop_one)
    with pytest.raises(ModelException) as info:
        similarity(driver, QUERY, TEXTS)
    assert info.value.code == LLMErrorCode.ERROR_GENERIC and info.value.retryable is False


@pytest.mark.parametrize("payload", [{"unexpected": 1}, [{"index": 0, "score": "x"}], [{"index": 9, "score": 0.1}], [{"index": 0, "score": 0.1}] * 2])
def test_malformed_tei_payloads_are_invalid_responses(payload):
    with pytest.raises(ModelException) as info:
        TEIRerank._parse(payload, 2)
    assert info.value.code == LLMErrorCode.ERROR_GENERIC


# --- SSRF, redirects and secrets -----------------------------------------------------------------------------------
def test_a_private_base_is_refused_before_any_request_when_private_addresses_are_not_allowed(fake_provider):  # noqa: F811
    with pytest.raises(ModelException) as info:
        similarity(make("TEI", "m", fake_provider.root, key=None, allow_private=False), QUERY, TEXTS)
    assert info.value.code == LLMErrorCode.ERROR_INVALID_REQUEST
    assert fake_provider.requests == []


@pytest.mark.parametrize("base", ["http://169.254.169.254", "http://[fd00:ec2::254]", "http://mysql:3306"])
def test_metadata_addresses_are_always_refused(base, fake_provider):  # noqa: F811
    with pytest.raises(ModelException) as info:
        similarity(make("TEI", "m", base, key=None, allow_private=True), QUERY, TEXTS)
    assert info.value.code == LLMErrorCode.ERROR_INVALID_REQUEST
    assert fake_provider.requests == []


def test_the_exact_default_tei_address_skips_the_guard_even_without_private_addresses():
    spec = resolve_provider("TEI")
    driver = make("TEI", "m", None, key=None, allow_private=False)
    assert driver.api_base == spec.default_base_url == "http://tei:80"
    assert driver._check_target(None) is None  # no DNS lookup, no refusal


def test_a_near_default_address_is_not_skipped():
    driver = make("TEI", "m", "http://tei:80/x", key=None, allow_private=False)
    with pytest.raises(ModelException):
        driver._check_target(None)


def test_a_key_echoed_by_the_provider_never_reaches_a_message_or_a_log(fake_provider, caplog):  # noqa: F811
    caplog.set_level(logging.DEBUG)
    with pytest.raises(ModelException) as info:
        similarity(openrouter(fake_provider, name="fake-secret-echo"), QUERY, TEXTS)
    text = f"{info.value} {info.value.safe_message} {caplog.text}"
    assert SECRET_ECHO_KEY not in text and FAKE_KEY not in text
    assert len(info.value.safe_message) <= 200


def test_the_key_is_not_in_the_repr_or_the_log_of_a_successful_call(fake_provider, caplog):  # noqa: F811
    caplog.set_level(logging.DEBUG)
    driver = openrouter(fake_provider)
    similarity(driver, QUERY, TEXTS)
    assert FAKE_KEY not in f"{driver!r} {caplog.text}"


def test_the_provider_registry_row_for_tei_is_rerank_only():
    spec = resolve_provider("TEI")
    assert spec.name == Provider.TEI and spec.model_types == ("rerank",) and spec.key == "none"
