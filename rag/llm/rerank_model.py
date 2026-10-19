"""Rerank drivers (plan 05-05, LLM-09, RETR-11, D-01, D-02, T-05-05-01..03).

``Base.similarity(query, texts)`` scores every text against the query and returns a ``RerankResult`` whose scores are in [0, 1]
(``normalize_rank``). Two drivers exist: ``TEIRerank`` (a text-embeddings-inference server, ``POST {base}/rerank``) and
``OpenRouterRerank`` (``POST {base}/rerank`` on OpenRouter's API with the workspace key). ``build_rerank`` picks one by provider.
The other direct drivers named in the docs (Jina, Cohere, NVIDIA, Voyage, LocalAI, DashScope) are not built (LLM-09 is Partial).

Safety rules mirror ``rag.llm.chat_model`` and ``rag.llm.embedding_model``:

* Each call builds its own ``httpx`` client with ``follow_redirects=False``; ``arun_with_retries`` is the only retry loop.
* The base URL is validated by ``common.net.url_guard`` before the first request and again before every attempt; only the exact
  documented default address of the provider skips the guard (string equality, nothing looser).
* Failure text comes from the parsed response body through ``ModelException`` (redacted, cut to 200 characters); the string form of a
  transport exception is never used, and the exception is raised outside the ``except`` block so no chained cause carries it.
* A response body is read with a size cap, so a hostile server cannot make the worker buffer an unbounded answer.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Collection, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from common.net.url_guard import UnsafeBaseUrl, ValidatedUrl, assert_unchanged, validate_base_url
from common.settings import LlmSettings
from rag.llm import Provider, ProviderSpec, validate_base_url_shape
from rag.llm.errors import LLMErrorCode, ModelException
from rag.llm.retry import arun_with_retries
from rag.llm.stream import Usage

logger = logging.getLogger(__name__)

TEI_BATCH_SIZE = 32
BATCH_TIMEOUT_SECONDS = 30.0
_BODY_LIMIT = 4 * 1024 * 1024
_ERROR_BODY_LIMIT = 65536
_MIN_SPAN = 1e-3


@dataclass(frozen=True)
class RerankResult:
    scores: list[float]
    tokens: int
    estimated: bool


def normalize_rank(scores: Sequence[float]) -> list[float]:
    """Scores in [0, 1]: unchanged when they already are, otherwise min-max; a span below 1e-3 is clipped instead (never NaN).

    A non-finite input counts as 0.0. The rule follows ``docs/11-llm/rerank-models.md``.
    """
    values = [float(s) if isinstance(s, (int, float)) and not isinstance(s, bool) and math.isfinite(s) else 0.0 for s in scores]
    if not values or all(0.0 <= v <= 1.0 for v in values):
        return values
    low, high = min(values), max(values)
    if high - low < _MIN_SPAN:
        return [min(1.0, max(0.0, v)) for v in values]
    return [(v - low) / (high - low) for v in values]


def _estimate_tokens(query: str, texts: Sequence[str]) -> int:
    try:
        from rag.nlp.token_count import count_tokens

        return count_tokens(query) + sum(count_tokens(t) for t in texts)
    except Exception:  # noqa: BLE001 - the vocabulary may be unavailable offline; a rough estimate is still useful
        return max(1, (len(query) + sum(len(t) for t in texts)) // 4)


def _retry_after(value: str | None) -> float | None:
    try:
        seconds = float(value) if value is not None else None
    except ValueError:
        return None
    return seconds if seconds is not None and seconds >= 0 else None


def _status_error(status: int, body: bytes | None, retry_after: float | None) -> ModelException:
    if status in (401, 403):
        return ModelException(LLMErrorCode.ERROR_AUTHENTICATION, provider_status=status, body=body)
    if status == 402:
        return ModelException(LLMErrorCode.ERROR_QUOTA, provider_status=status, body=body)
    if status == 429:
        return ModelException(LLMErrorCode.ERROR_RATE_LIMIT, retryable=True, provider_status=status, retry_after=retry_after, body=body)
    if status == 503:
        return ModelException(LLMErrorCode.ERROR_SERVER, retryable=True, provider_status=status, retry_after=retry_after, body=body)
    if status == 408:
        return ModelException(LLMErrorCode.ERROR_TIMEOUT, retryable=True, provider_status=status, retry_after=retry_after, body=body)
    if 400 <= status < 500:  # 413, 422 and 424 included: the request itself was refused
        return ModelException(LLMErrorCode.ERROR_INVALID_REQUEST, provider_status=status, body=body)
    if status >= 500:
        return ModelException(LLMErrorCode.ERROR_SERVER, provider_status=status, body=body)
    return ModelException(LLMErrorCode.ERROR_GENERIC, provider_status=status)  # 3xx (never followed) and anything unexpected


def _invalid_response() -> ModelException:
    return ModelException(LLMErrorCode.ERROR_GENERIC, message="provider returned an unexpected rerank answer")


def _score(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise _invalid_response()
    return float(value)


def _by_index(rows: Any, size: int, score_key: str) -> list[float]:
    """Scores placed at their ``index``; every index of the batch must appear exactly once."""
    if not isinstance(rows, list) or len(rows) != size:
        raise _invalid_response()
    scores: list[float | None] = [None] * size
    for row in rows:
        index = row.get("index") if isinstance(row, dict) else None
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < size or scores[index] is not None:
            raise _invalid_response()
        scores[index] = _score(row.get(score_key))
    return [s for s in scores if s is not None]


class Base(ABC):
    """Rerank driver interface. Subclasses build one request (``_request``) and read one answer (``_parse``)."""

    def __init__(
        self,
        provider_spec: ProviderSpec,
        model_name: str,
        api_key: str | None,
        api_base: str | None,
        api_version: str | None = None,
        *,
        llm_settings: LlmSettings,
        allow_private: bool,
        deny_hosts: Collection[str] = (),
        sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
        timeout: float | None = None,
    ) -> None:
        self.spec = provider_spec
        self.model_name = model_name
        self._api_key = api_key
        self.api_base = (api_base or provider_spec.default_base_url or "").strip().rstrip("/") or None
        self.api_version = api_version
        self.llm_settings = llm_settings
        self.allow_private = allow_private
        self.deny_hosts = tuple(deny_hosts)
        self._sleep = sleep
        self.timeout = float(timeout if timeout is not None else BATCH_TIMEOUT_SECONDS)
        self.last_usage: Usage | None = None

    def __repr__(self) -> str:
        return f"{type(self).__name__}(provider={self.spec.name!r}, model={self.model_name!r})"

    def _check_target(self, validated: ValidatedUrl | None) -> ValidatedUrl | None:
        """Shape check, then SSRF check before an attempt (re-checked on later ones against DNS rebinding)."""
        problem = validate_base_url_shape(self.spec, self.api_base)
        if problem is not None or self.api_base is None:
            raise ModelException(LLMErrorCode.ERROR_INVALID_REQUEST, message=f"base URL rejected: {problem or 'base_url_required'}")
        if self.api_base == self.spec.default_base_url:
            return None  # the documented address of this provider
        try:
            if validated is None:
                return validate_base_url(self.api_base, allow_private=self.allow_private, deny_hosts=self.deny_hosts)
            return assert_unchanged(validated, self.api_base, allow_private=self.allow_private, deny_hosts=self.deny_hosts)
        except UnsafeBaseUrl as refused:
            reason = refused.reason
        raise ModelException(LLMErrorCode.ERROR_INVALID_REQUEST, message=f"base URL rejected: {reason}")

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if self._api_key:
            headers["authorization"] = f"Bearer {self._api_key}"
        return headers

    @abstractmethod
    def _request(self, query: str, batch: list[str]) -> dict[str, Any]: ...

    @staticmethod
    @abstractmethod
    def _parse(payload: Any, size: int) -> list[float]: ...

    def _usage_of(self, payload: Any) -> int | None:
        del payload
        return None

    async def _post(self, client: httpx.AsyncClient, body: dict[str, Any]) -> Any:
        """One bounded POST. Returns the parsed JSON, or raises the typed error for the status (outside the ``except`` block)."""
        failure: ModelException | None = None
        status, retry_after, raw = 0, None, bytearray()
        try:
            async with client.stream("POST", f"{self.api_base}/rerank", json=body, headers=self._headers()) as response:
                status, retry_after = response.status_code, _retry_after(response.headers.get("retry-after"))
                limit = _BODY_LIMIT if status < 300 else _ERROR_BODY_LIMIT
                async for piece in response.aiter_bytes():
                    raw += piece
                    if len(raw) > limit:
                        break
        except (TimeoutError, httpx.TimeoutException):
            failure = ModelException(LLMErrorCode.ERROR_TIMEOUT, retryable=True)
        except (httpx.TransportError, OSError):
            failure = ModelException(LLMErrorCode.ERROR_CONNECTION)
        if failure is not None:
            raise failure
        if status >= 300:
            raise _status_error(status, bytes(raw[:_ERROR_BODY_LIMIT]), retry_after)
        if len(raw) > _BODY_LIMIT:
            raise _invalid_response()
        try:
            return json.loads(bytes(raw))
        except ValueError:
            pass
        raise _invalid_response()

    async def _attempt(self, client: httpx.AsyncClient, state: dict[str, Any], query: str, batch: list[str]) -> tuple[list[float], int | None]:
        state["validated"] = self._check_target(state.get("validated"))
        failure: ModelException | None = None
        try:
            payload = await self._post(client, self._request(query, batch))
            return self._parse(payload, len(batch)), self._usage_of(payload)
        except ModelException as exc:
            failure = exc
        logger.warning("rerank call failed provider=%s model=%s code=%s", self.spec.name, self.model_name, failure.code.value)
        raise failure

    def _batches(self, texts: list[str]) -> list[list[str]]:
        return [texts]

    async def similarity(self, query: str, texts: list[str]) -> RerankResult:
        """Scores in [0, 1], one per text, in the order given. An empty query or no texts costs no request."""
        if not texts or not (query or "").strip():
            self.last_usage = Usage(0, 0, 0, False)
            return RerankResult([0.0] * len(texts), 0, False)
        state: dict[str, Any] = {"validated": self._check_target(None)}  # refuse a bad target before any client exists
        raw: list[float] = []
        reported: int | None = 0
        async with httpx.AsyncClient(follow_redirects=False, timeout=self.timeout) as client:
            for batch in self._batches(texts):
                got, used = await arun_with_retries(
                    lambda b=batch: self._attempt(client, state, query, b), max_retries=self.llm_settings.max_retries, sleep=self._sleep
                )
                raw.extend(got)
                reported = None if used is None or reported is None else reported + used
        estimated = reported is None or reported <= 0
        tokens = _estimate_tokens(query, texts) if estimated else int(reported or 0)
        self.last_usage = Usage(tokens, 0, tokens, estimated)
        return RerankResult(normalize_rank(raw), tokens, estimated)


class TEIRerank(Base):
    """text-embeddings-inference: ``POST {base}/rerank`` with ``{query, texts, raw_scores, truncate}`` in batches of 32 (D-01)."""

    def _batches(self, texts: list[str]) -> list[list[str]]:
        return [texts[start : start + TEI_BATCH_SIZE] for start in range(0, len(texts), TEI_BATCH_SIZE)]

    def _request(self, query: str, batch: list[str]) -> dict[str, Any]:
        return {"query": query, "texts": batch, "raw_scores": False, "truncate": True}

    @staticmethod
    def _parse(payload: Any, size: int) -> list[float]:
        return _by_index(payload, size, "score")


class OpenRouterRerank(Base):
    """OpenRouter's rerank API: ``POST {base}/rerank`` with ``{model, query, documents, top_n}`` and the workspace key (D-02, R-207)."""

    def _request(self, query: str, batch: list[str]) -> dict[str, Any]:
        return {"model": self.model_name, "query": query, "documents": batch, "top_n": len(batch)}

    @staticmethod
    def _parse(payload: Any, size: int) -> list[float]:
        results = payload.get("results") if isinstance(payload, dict) else None
        return _by_index(results, size, "relevance_score")

    def _usage_of(self, payload: Any) -> int | None:
        usage = payload.get("usage") if isinstance(payload, dict) else None
        total = usage.get("total_tokens") if isinstance(usage, dict) else None
        return total if isinstance(total, int) and not isinstance(total, bool) and total > 0 else None


def build_rerank(
    spec: ProviderSpec,
    model_name: str,
    api_key: str | None,
    api_base: str | None,
    api_version: str | None = None,
    *,
    llm_settings: LlmSettings,
    allow_private: bool,
    deny_hosts: Collection[str] = (),
    sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
    timeout: float | None = None,
) -> Base:
    """Pick the driver for ``spec`` (``ValueError`` when the provider has none). Construction does no I/O."""
    kind: type[Base]
    if spec.name == Provider.TEI:
        kind = TEIRerank
    elif spec.name == Provider.OPENROUTER:
        kind = OpenRouterRerank
    else:
        raise ValueError(f"provider {spec.name!r} has no rerank driver")
    return kind(
        spec, model_name, api_key, api_base, api_version,
        llm_settings=llm_settings, allow_private=allow_private, deny_hosts=deny_hosts, sleep=sleep, timeout=timeout,
    )  # fmt: skip
