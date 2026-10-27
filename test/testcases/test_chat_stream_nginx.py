"""SSE delivery and cancellation through the running Nginx ingress."""
# ruff: noqa: F401, F811 -- pytest discovers imported fixtures and test parameters shadow their names.
from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from rag.prompts.citations import canonicalise
from test.helpers.fake_provider import FakeProvider
from test.helpers.planted import FACTS
from test.helpers.wait import wait_until
from test.testcases.test_chat_flow import COMPLETIONS, assistant, fake, registry, world  # noqa: F401
from test.testcases.test_provider_flow import COMPAT, api, ok, sql

pytestmark = pytest.mark.e2e


def _frames(response: httpx.Response):
    for line in response.iter_lines():
        if line.startswith("data: "):
            yield line[6:]


def test_first_frame_before_last_through_ingress(ingress: httpx.Client, world: SimpleNamespace, fake: FakeProvider) -> None:
    chat = assistant(ingress, world.owner)
    fake.hold_chat()
    fake.chat_mode = "gated"
    try:
        with ingress.stream(
            "POST", COMPLETIONS,
            headers={"Authorization": f"Bearer {world.owner.token}"},
            json={"chat_id": chat["id"], "message": "hello", "stream": True},
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            assert response.headers["x-accel-buffering"] == "no"
            assert "content-length" not in response.headers
            assert "gzip" not in response.headers.get("content-encoding", "")
            frames = _frames(response)
            first = json.loads(next(frames))
            assert first["code"] == 0 and first["data"]["final"] is False
            assert fake._chat_gate is not None and not fake._chat_gate.is_set()
            fake.release_chat()
            remaining = list(frames)
            assert remaining[-1] == "[DONE]"
            final = json.loads(remaining[-2])["data"]
            assert final["final"] is True and final["finish"] == "complete"
    finally:
        fake.release_chat()
        fake.chat_mode = "marker"


def test_stop_persists_partial_and_releases_lock(ingress: httpx.Client, world: SimpleNamespace, fake: FakeProvider) -> None:
    chat = assistant(ingress, world.owner)
    fake.hold_chat()
    fake.chat_mode = "gated"
    first: dict = {}
    try:
        with ingress.stream(
            "POST", COMPLETIONS,
            headers={"Authorization": f"Bearer {world.owner.token}"},
            json={"chat_id": chat["id"], "message": "hello", "stream": True},
        ) as response:
            assert response.status_code == 200
            first = json.loads(next(_frames(response)))
            assert first["data"]["answer"]
            assert fake._chat_gate is not None and not fake._chat_gate.is_set()
        session_id = first["data"]["session_id"]

        def stopped() -> dict | None:
            messages = ok(api(ingress, "GET", f"/api/v1/chats/{chat['id']}/sessions/{session_id}", world.owner.token))["messages"]
            return messages[-1] if messages and messages[-1].get("finish") == "stopped" else None

        stored = wait_until(stopped, timeout=20, interval=0.2)
        assert stored["content"] == canonicalise(first["data"]["answer"], 0)
        assert stored["usage"]["estimated"] is True
        fake.release_chat()
        fake.chat_mode = "marker"
        next_turn = api(ingress, "POST", COMPLETIONS, world.owner.token, body={"chat_id": chat["id"], "session_id": session_id, "message": "follow up", "stream": False})
        assert next_turn.status_code == 200
    finally:
        fake.release_chat()
        fake.chat_mode = "marker"


def test_turn_in_progress_while_streaming(ingress: httpx.Client, world: SimpleNamespace, fake: FakeProvider) -> None:
    chat = assistant(ingress, world.owner)
    fake.hold_chat()
    fake.chat_mode = "gated"
    try:
        with ingress.stream(
            "POST", COMPLETIONS,
            headers={"Authorization": f"Bearer {world.owner.token}"},
            json={"chat_id": chat["id"], "message": "hello", "stream": True},
        ) as response:
            frames = _frames(response)
            first = json.loads(next(frames))["data"]
            blocked = api(ingress, "POST", COMPLETIONS, world.owner.token,
                          body={"chat_id": chat["id"], "session_id": first["session_id"], "message": "second", "stream": False})
            assert blocked.status_code == 409 and blocked.json()["data"]["reason"] == "turn_in_progress"
            fake.release_chat()
            assert list(frames)[-1] == "[DONE]"
    finally:
        fake.release_chat()
        fake.chat_mode = "marker"


def test_prebyte_refusal_remains_json_through_ingress(ingress: httpx.Client, world: SimpleNamespace) -> None:
    chat = assistant(ingress, world.owner)
    response = api(ingress, "POST", COMPLETIONS, world.owner.token,
                   body={"chat_id": chat["id"], "message": "   ", "stream": True})
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["data"]["reason"] == "question_invalid"


def test_long_stream_crosses_multiple_network_reads(ingress: httpx.Client, world: SimpleNamespace, fake: FakeProvider) -> None:
    chat = assistant(ingress, world.owner)
    fake.chat_mode = "long"
    try:
        with ingress.stream(
            "POST", COMPLETIONS,
            headers={"Authorization": f"Bearer {world.owner.token}"},
            json={"chat_id": chat["id"], "message": "hello", "stream": True},
        ) as response:
            assert response.status_code == 200
            chunks = list(response.iter_raw())
            assert len(chunks) > 1 and sum(map(len, chunks)) > 12 * 1024
            assert b"data: [DONE]\n\n" in b"".join(chunks)
    finally:
        fake.chat_mode = "marker"


def test_stopped_citation_keeps_sparse_index_and_charges_usage(ingress: httpx.Client, world: SimpleNamespace, fake: FakeProvider) -> None:
    chat = assistant(ingress, world.owner, dataset_ids=[world.planted.dataset_id], vector_similarity_weight=1, similarity_threshold=0, top_n=6)

    def counter() -> int:
        rows = sql("SELECT `used_tokens` FROM `tenant_llm` WHERE `tenant_id`=%s AND `llm_factory`=%s AND `llm_name`=%s",
                   (world.owner.tenant_id, COMPAT, "fake-chat"))
        return int(rows[0][0])
    before = counter()
    fake.hold_chat()
    fake.chat_mode = "gated"
    try:
        with ingress.stream(
            "POST", COMPLETIONS,
            headers={"Authorization": f"Bearer {world.owner.token}"},
            json={"chat_id": chat["id"], "message": FACTS[0].question, "stream": True},
        ) as response:
            assert response.status_code == 200
            first = json.loads(next(_frames(response)))["data"]
            assert first["answer"] == "Start ##2$$ "

        def stopped() -> dict | None:
            messages = ok(api(ingress, "GET", f"/api/v1/chats/{chat['id']}/sessions/{first['session_id']}", world.owner.token))["messages"]
            return messages[-1] if messages and messages[-1].get("finish") == "stopped" else None

        saved = wait_until(stopped, timeout=20, interval=0.2)
        assert saved["content"] == first["answer"]
        assert [chunk["index"] for chunk in saved["reference"]["chunks"]] == [2]
        assert saved["reference"]["doc_aggs"][0]["count"] == 1
        assert saved["usage"]["estimated"] is True
        wait_until(lambda: counter() >= before + saved["usage"]["total"], timeout=10, interval=0.1)
    finally:
        fake.release_chat()
        fake.chat_mode = "marker"
