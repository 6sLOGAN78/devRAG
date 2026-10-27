"""The completion stream's exact wire frames."""
from __future__ import annotations

import json

import pytest

from api.apps.sse_frames import DONE, delta_frame, error_frame, final_frame, frame

pytestmark = pytest.mark.unit


def decoded(raw: bytes) -> dict:
    assert raw.startswith(b"data: ") and raw.endswith(b"\n\n")
    return json.loads(raw[6:-2])


def test_frame_keeps_envelope_order_and_unicode() -> None:
    raw = frame({"answer": "你好"})
    assert raw.startswith(b'data: {"code": 0, "message": "", "data": ')
    assert "你好".encode() in raw
    assert decoded(raw) == {"code": 0, "message": "", "data": {"answer": "你好"}}


def test_non_finite_reference_number_is_null() -> None:
    data = {"reference": {"chunks": [{"similarity": float("nan"), "vector_similarity": float("inf")}]}}
    assert decoded(frame(data))["data"]["reference"]["chunks"] == [{"similarity": None, "vector_similarity": None}]


def test_delta_frame_has_no_reference_or_final_usage() -> None:
    data = decoded(delta_frame("session", "message", "a"))["data"]
    assert data == {"answer": "a", "reference": None, "session_id": "session", "message_id": "message", "final": False}


def test_final_frame_and_done() -> None:
    final = {"answer": "done", "reference": {"chunks": [], "doc_aggs": []}, "finish": "complete", "final": True}
    assert decoded(final_frame(final))["data"] == final
    assert DONE == b"data: [DONE]\n\n"


def test_error_frame_carries_reason_and_nonzero_code() -> None:
    result = decoded(error_frame(101, "provider failed", "session", "message", "provider_unreachable"))
    assert result == {
        "code": 101, "message": "provider failed",
        "data": {"session_id": "session", "message_id": "message", "reason": "provider_unreachable", "final": True},
    }
