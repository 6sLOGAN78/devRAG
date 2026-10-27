"""The real Quart completion response keeps a gated stream alive past Quart's default timeout."""
# ruff: noqa: F401, F811 -- imported fixtures are discovered by pytest and shadowed by test parameters.
from __future__ import annotations

import asyncio
import dataclasses
import json
import threading
import time

import pytest

from api.apps import create_app
from api.db.services import conversation_service
from api.db.services.auth_service import Principal
from test.helpers.app import STUB_SECRET, StubPrincipalResolver
from test.helpers.wait import wait_until
from test.integration.test_chat_turn_service import fake, new_chat, registry, world  # noqa: F401 -- fixture imports
from test.integration.test_knowledgebase_service import principal_of
from test.integration.test_upload_service import _bound_database  # noqa: F401

pytestmark = pytest.mark.integration
COMPLETIONS = "/api/v1/chat/completions"
DONE = b"data: [DONE]\n\n"


def _data(raw: bytes) -> dict:
    assert raw.startswith(b"data: ") and raw.endswith(b"\n\n"), raw
    return json.loads(raw[6:-2])


async def _next_frame(connection) -> bytes:
    while True:
        raw = await asyncio.wait_for(connection.receive(), timeout=10)
        if raw.startswith(b"data: "):
            return raw
        if raw:
            raise AssertionError(f"expected an SSE frame, got HTTP {connection.status_code}: {raw[:240]!r}")


def _app(world, principal: Principal, *, deadline: int | None = None):
    resolver = StubPrincipalResolver(principal=principal)
    settings = dataclasses.replace(world.embed_settings, security=dataclasses.replace(world.embed_settings.security, secret_key=STUB_SECRET))
    if deadline is not None:
        settings = dataclasses.replace(settings, chat=dataclasses.replace(settings.chat, stream_deadline_seconds=deadline))
    app = create_app(settings, principal_resolver=resolver)
    app.config["RESPONSE_TIMEOUT"] = 1
    return app, resolver.token


@pytest.mark.asyncio
async def test_response_timeout_is_overridden_for_a_gated_provider(world, fake) -> None:
    fake.reset()
    fake.chat_mode = "gated"
    chat = new_chat(world, bound=False)
    principal = principal_of(world.owner)
    app, token = _app(world, principal)
    body = json.dumps({"chat_id": chat, "message": "hello", "stream": True}).encode()
    try:
        async with app.test_client().request(COMPLETIONS, method="POST", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}) as conn:
            await conn.send(body)
            await conn.send_complete()
            first = _data(await _next_frame(conn))
            assert conn.status_code == 200 and first["data"]["final"] is False
            assert conn.headers is not None and conn.headers["Cache-Control"] == "no-cache"
            start = time.monotonic()
            await asyncio.to_thread(wait_until, lambda: time.monotonic() - start >= 1.5, timeout=3, interval=0.05)
            fake.release_chat()
            frames: list[bytes] = []
            while not frames or frames[-1] != DONE:
                frames.append(await _next_frame(conn))
            assert any(_data(raw)["data"].get("final") is True for raw in frames[:-1])
            assert frames[-1] == DONE
        session = first["data"]["session_id"]
        saved = conversation_service.get_session(principal, chat, session)["messages"]
        assert saved[-1]["finish"] == "complete"
    finally:
        fake.release_chat()
        fake.chat_mode = "marker"


@pytest.mark.asyncio
async def test_prebyte_invalid_question_keeps_a_json_http_error(world) -> None:
    chat = new_chat(world, bound=False)
    app, token = _app(world, principal_of(world.owner))
    response = await app.test_client().post(COMPLETIONS, headers={"Authorization": f"Bearer {token}"}, json={"chat_id": chat, "message": "   ", "stream": True})
    assert response.status_code == 400 and response.headers["Content-Type"].startswith("application/json")
    assert (await response.get_json())["data"]["reason"] == "question_invalid"


@pytest.mark.asyncio
async def test_stop_before_first_token_stores_empty_stopped_message(world, fake) -> None:
    fake.reset()
    fake.hold_chat()
    fake.chat_mode = "gated_before_first"
    chat = new_chat(world, bound=False)
    principal = principal_of(world.owner)
    session_id = conversation_service.create_session(principal, chat, "stop before read")["id"]
    app, token = _app(world, principal)
    body = json.dumps({"chat_id": chat, "session_id": session_id, "message": "hello", "stream": True}).encode()
    try:
        async with app.test_client().request(COMPLETIONS, method="POST", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}) as conn:
            await conn.send(body)
            await conn.send_complete()
            # The provider has opened but has not emitted its first content token.
            await asyncio.to_thread(wait_until, lambda: bool(fake.chat_requests()), timeout=5, interval=0.01)
            await conn.disconnect()

        def stopped() -> dict | None:
            messages = conversation_service.get_session(principal, chat, session_id)["messages"]
            return messages[-1] if messages and messages[-1].get("finish") == "stopped" else None

        saved = await asyncio.to_thread(wait_until, stopped, timeout=6, interval=0.1)
        assert saved["content"] == ""
        assert saved["usage"]["estimated"] is True
    finally:
        fake.release_chat()
        fake.chat_mode = "marker"


@pytest.mark.asyncio
async def test_stream_deadline_cuts_a_held_provider_and_stores_partial(world, fake) -> None:
    fake.reset()
    fake.hold_chat()
    fake.chat_mode = "gated"
    chat = new_chat(world, bound=False)
    principal = principal_of(world.owner)
    app, token = _app(world, principal, deadline=8)
    body = json.dumps({"chat_id": chat, "message": "hello", "stream": True}).encode()
    try:
        async with app.test_client().request(COMPLETIONS, method="POST", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}) as conn:
            await conn.send(body)
            await conn.send_complete()
            first = _data(await _next_frame(conn))["data"]
            assert first["final"] is False

            def stopped() -> dict | None:
                messages = conversation_service.get_session(principal, chat, first["session_id"])["messages"]
                return messages[-1] if messages and messages[-1].get("finish") in {"stopped", "failed"} else None

            saved = await asyncio.to_thread(wait_until, stopped, timeout=12, interval=0.1)
            assert saved["content"] and saved["usage"]["estimated"] is True
    finally:
        fake.release_chat()
        fake.chat_mode = "marker"


@pytest.mark.asyncio
async def test_slow_finalization_keeps_the_turn_exclusive(world, fake, monkeypatch) -> None:
    """A stream nearing its lease expiry must retain exclusivity while finalization is still running."""
    fake.reset()
    fake.hold_chat()
    fake.chat_mode = "gated"
    chat = new_chat(world, bound=False)
    app, token = _app(world, principal_of(world.owner), deadline=8)
    from api.db.services import chat_turn_service

    acquire, finalise = conversation_service.acquire_turn, chat_turn_service.finalise
    held: dict = {}
    finishing, release = threading.Event(), threading.Event()

    def capture_lock(*args):
        lock = acquire(*args)
        held["lock"] = lock
        return lock

    def slow_finalise(*args):
        finishing.set()
        if not release.wait(timeout=10):
            raise TimeoutError("test finalization was not released")
        return finalise(*args)

    monkeypatch.setattr(conversation_service, "acquire_turn", capture_lock)
    monkeypatch.setattr(chat_turn_service, "finalise", slow_finalise)
    body = json.dumps({"chat_id": chat, "message": "hello", "stream": True}).encode()
    try:
        async with app.test_client().request(COMPLETIONS, method="POST", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}) as conn:
            await conn.send(body)
            await conn.send_complete()
            first = _data(await _next_frame(conn))["data"]
            lock = held["lock"]
            lock._client.expire(lock.key, 1)  # simulate a long stream consuming nearly all of its lease
            fake.release_chat()
            assert await asyncio.to_thread(finishing.wait, 5)
            start = time.monotonic()
            await asyncio.to_thread(wait_until, lambda: time.monotonic() - start >= 1.5, timeout=3, interval=0.05)
            try:
                other = await asyncio.to_thread(acquire, world.embed_settings, first["session_id"])
            except conversation_service.ServiceError as exc:
                assert exc.reason == "turn_in_progress"
            else:
                other.release()
                pytest.fail("a competing turn acquired the lock during finalization")
            release.set()
            while await _next_frame(conn) != DONE:
                pass
    finally:
        release.set()
        fake.release_chat()
        fake.chat_mode = "marker"


@pytest.mark.asyncio
async def test_nonstream_finalization_timeout_cannot_later_store_a_complete_answer(world, fake, monkeypatch) -> None:
    from api.db.services import chat_turn_service

    fake.reset()
    fake.chat_mode = "marker"
    chat = new_chat(world, bound=False)
    principal = principal_of(world.owner)
    session_id = conversation_service.create_session(principal, chat)["id"]
    # Warm the local SDK before the intentionally short finalization deadline.
    await asyncio.to_thread(chat_turn_service.complete_turn, world.embed_settings, principal, {"chat_id": chat, "message": "warmup"})
    app, token = _app(world, principal, deadline=1)
    finalise = chat_turn_service.finalise
    finishing, release, finished = threading.Event(), threading.Event(), threading.Event()

    def slow_finalise(*args):
        finishing.set()
        if not release.wait(timeout=10):
            raise TimeoutError("test finalization was not released")
        result = finalise(*args)
        finished.set()
        return result

    monkeypatch.setattr(chat_turn_service, "finalise", slow_finalise)
    task = asyncio.create_task(app.test_client().post(COMPLETIONS, headers={"Authorization": f"Bearer {token}"},
                                                    json={"chat_id": chat, "session_id": session_id, "message": "hello", "stream": False}))
    try:
        assert await asyncio.to_thread(finishing.wait, 5)
        response = await asyncio.wait_for(task, timeout=2)
        assert response.status_code == 504
        assert (await response.get_json())["data"]["reason"] == "provider_timeout"
        saved = conversation_service.get_session(principal, chat, session_id)["messages"]
        assert saved[-1]["finish"] == "failed"
        release.set()
        assert await asyncio.to_thread(finished.wait, 5)
        saved = conversation_service.get_session(principal, chat, session_id)["messages"]
        assert saved[-1]["finish"] == "failed"
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
