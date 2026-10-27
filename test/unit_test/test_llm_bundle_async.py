"""Async bundle usage writes stay off the request loop."""
from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest

from api.db.services.llm_service import LLMBundle
from rag.llm.stream import Usage


class Driver:
    def __init__(self) -> None:
        self.last_usage: Usage | None = None

    async def async_chat(self, *_: object) -> tuple[str, None]:
        self.last_usage = Usage(2, 3, 5)
        return "answer", None

    async def async_chat_streamly(self, *_: object) -> AsyncIterator[str]:
        yield "answer"
        self.last_usage = Usage(2, 3, 5)


def bundle_with_recorder(monkeypatch: pytest.MonkeyPatch, seen: list[threading.Thread]) -> LLMBundle:
    bundle = LLMBundle.__new__(LLMBundle)
    driver = Driver()
    bundle._driver = driver
    bundle._last_usage = None
    monkeypatch.setattr(bundle, "_chat_driver", lambda: driver)

    def report(usage: Usage | None) -> None:
        assert usage is not None and usage.total_tokens == 5
        seen.append(threading.current_thread())

    monkeypatch.setattr(bundle, "_report_usage", report)
    return bundle


@pytest.mark.asyncio
async def test_report_usage_runs_off_the_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[threading.Thread] = []
    bundle = bundle_with_recorder(monkeypatch, seen)
    loop_thread = threading.current_thread()
    assert await bundle.async_chat("system", []) == "answer"
    assert len(seen) == 1 and seen[0] is not loop_thread


@pytest.mark.asyncio
async def test_stream_usage_write_cannot_run_on_the_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[threading.Thread] = []
    bundle = bundle_with_recorder(monkeypatch, seen)
    loop_thread = threading.current_thread()

    def db_write(usage: Usage | None) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            pytest.fail("a usage database write ran on the event loop")
        assert usage is not None
        seen.append(threading.current_thread())

    monkeypatch.setattr(bundle, "_report_usage", db_write)
    assert [piece async for piece in bundle.async_chat_streamly("system", [])] == ["answer"]
    assert len(seen) == 1 and seen[0] is not loop_thread


@pytest.mark.asyncio
async def test_counter_failure_does_not_lose_paid_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = bundle_with_recorder(monkeypatch, [])
    bundle.tenant_id = "tenant"
    bundle._spec = SimpleNamespace(name="fake")
    bundle.ref = SimpleNamespace(model="fake-chat")
    monkeypatch.setattr(bundle, "_report_usage", lambda _usage: (_ for _ in ()).throw(RuntimeError("counter unavailable")))
    assert await bundle.async_chat("system", []) == "answer"
