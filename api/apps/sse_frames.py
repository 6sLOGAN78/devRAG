"""Small, explicit SSE frames for cited chat completions."""
from __future__ import annotations

import json
from typing import Any

from rag.nlp.fusion import sanitize_floats

DONE = b"data: [DONE]\n\n"


def _wire(code: int, message: str, data: dict[str, Any]) -> bytes:
    body = {"code": code, "message": message, "data": sanitize_floats(data)}
    return b"data: " + json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n\n"


def frame(data: dict[str, Any]) -> bytes:
    return _wire(0, "", data)


def delta_frame(session_id: str, message_id: str, text: str) -> bytes:
    return frame({"answer": text, "reference": None, "session_id": session_id, "message_id": message_id, "final": False})


def final_frame(final: dict[str, Any]) -> bytes:
    return frame(final)


def error_frame(code: int, message: str, session_id: str, message_id: str, reason: str) -> bytes:
    return _wire(code, message, {"session_id": session_id, "message_id": message_id, "reason": reason, "final": True})
