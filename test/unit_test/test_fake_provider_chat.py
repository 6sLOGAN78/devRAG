"""Plan 05-01: the fake provider's gated chat stream, chat-request record and rerank endpoints (D-06, D-21)."""
from __future__ import annotations

import json
import threading
from collections.abc import Iterator

import httpx
import pytest

from test.helpers.fake_provider import CHAT_TEXT, FakeProvider, running_fake_provider
from test.helpers.wait import wait_until

pytestmark = pytest.mark.unit



@pytest.fixture
def provider() -> Iterator[FakeProvider]:
    with running_fake_provider() as running:
        yield running


BODY = {"model": "fake-chat", "stream": True, "messages": [{"role": "user", "content": "hi"}]}


def _pieces(lines: Iterator[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        if not line.startswith("data: ") or line.strip() == "data: [DONE]":
            continue
        for choice in json.loads(line[6:]).get("choices", []):
            text = choice.get("delta", {}).get("content")
            if text:
                out.append(text)
    return out


def _stream_pieces(provider: FakeProvider, mode: str) -> list[str]:
    provider.chat_mode = mode
    with httpx.stream("POST", f"{provider.base_url}/chat/completions", json=BODY, timeout=10) as response:
        assert response.status_code == 200
        return _pieces(response.iter_lines())


def test_plain_mode_streams_the_default_text(provider: FakeProvider) -> None:
    assert "".join(_stream_pieces(provider, "plain")) == CHAT_TEXT


def test_marker_mode_streams_a_whole_marker(provider: FakeProvider) -> None:
    pieces = _stream_pieces(provider, "marker")
    assert "".join(pieces) == "Answer text ##0$$ more."
    assert "##0$$" in pieces


def test_split_marker_mode_splits_the_marker_over_two_pieces(provider: FakeProvider) -> None:
    pieces = _stream_pieces(provider, "split_marker")
    assert "".join(pieces) == "See ##1$$ end."
    assert "##" in pieces and "1$$" in pieces
    assert "##1$$" not in pieces


def test_gated_mode_holds_the_stream_until_released(provider: FakeProvider) -> None:
    provider.chat_mode = "gated"
    received: list[str] = []
    with httpx.stream("POST", f"{provider.base_url}/chat/completions", json=BODY, timeout=10) as response:
        lines = response.iter_lines()
        first: list[str] = []
        for line in lines:
            first.append(line)
            if "Start ##2$$" in line:
                break
        received.extend(_pieces(iter(first)))
        assert received == ["Start ##2$$ "]
        # Nothing more arrives while the gate is closed: the reader must still be blocked after a short deadline.
        rest: list[str] = []
        done = threading.Event()

        def drain() -> None:
            rest.extend(_pieces(lines))
            done.set()

        threading.Thread(target=drain, daemon=True).start()
        with pytest.raises(TimeoutError):
            wait_until(done.is_set, timeout=0.4, interval=0.05)
        provider.release_chat()
        wait_until(done.is_set, timeout=10, interval=0.02)
    assert "".join(received + rest) == "Start ##2$$ end."


def test_error_midstream_closes_without_done(provider: FakeProvider) -> None:
    provider.chat_mode = "error_midstream"
    seen: list[str] = []
    with pytest.raises(httpx.HTTPError):  # the connection is cut, so the chunked body is incomplete
        with httpx.stream("POST", f"{provider.base_url}/chat/completions", json=BODY, timeout=10) as response:
            for line in response.iter_lines():
                seen.append(line)
    assert _pieces(iter(seen)) and "data: [DONE]" not in seen


def test_chat_requests_are_recorded_in_order(provider: FakeProvider) -> None:
    assert provider.chat_requests() == []
    for text in ("one", "two"):
        httpx.post(f"{provider.base_url}/chat/completions", json={"model": "m", "messages": [{"role": "user", "content": text}]}, timeout=10)
    httpx.post(f"{provider.base_url}/embeddings", json={"model": "m", "input": ["x"]}, timeout=10)
    bodies = provider.chat_requests()
    assert [b["messages"][0]["content"] for b in bodies] == ["one", "two"]


def test_tei_rerank_scores_by_query_word_overlap_and_sorts(provider: FakeProvider) -> None:
    body = {"query": "red fox jumps", "texts": ["a blue cat", "the red fox", "red fox jumps high"], "raw_scores": False, "truncate": True}
    response = httpx.post(f"{provider.root}/rerank", json=body, timeout=10)
    assert response.status_code == 200
    rows = response.json()
    assert [r["index"] for r in rows] == [2, 1, 0]
    assert rows[0]["score"] == pytest.approx(1.0)
    assert rows[1]["score"] == pytest.approx(2 / 3)
    assert rows[2]["score"] == 0.0


def test_tei_rerank_refuses_more_than_32_texts(provider: FakeProvider) -> None:
    response = httpx.post(f"{provider.root}/rerank", json={"query": "q", "texts": ["t"] * 33}, timeout=10)
    assert response.status_code == 413
    payload = response.json()
    assert "error" in payload and "error_type" in payload
    assert httpx.post(f"{provider.root}/rerank", json={"query": "q", "texts": ["t"] * 32}, timeout=10).status_code == 200


def test_openrouter_rerank_shape(provider: FakeProvider) -> None:
    body = {"model": "cohere/rerank-v3.5", "query": "red fox", "documents": ["blue cat", "red fox", "fox"], "top_n": 2}
    response = httpx.post(f"{provider.root}/api/v1/rerank", json=body, timeout=10)
    assert response.status_code == 200
    payload = response.json()
    results = payload["results"]
    assert [r["index"] for r in results] == [1, 2]
    assert results[0]["relevance_score"] == pytest.approx(1.0)
    assert results[0]["document"] == {"text": "red fox"}
    assert set(payload["usage"]) == {"search_units", "total_tokens"}


def test_rerank_model_named_fake_rerank_500_answers_500_on_both(provider: FakeProvider) -> None:
    tei = httpx.post(f"{provider.root}/rerank", json={"model": "fake-rerank-500", "query": "q", "texts": ["t"]}, timeout=10)
    openrouter = httpx.post(f"{provider.root}/api/v1/rerank", json={"model": "fake-rerank-500", "query": "q", "documents": ["t"]}, timeout=10)
    assert tei.status_code == 500 and openrouter.status_code == 500
