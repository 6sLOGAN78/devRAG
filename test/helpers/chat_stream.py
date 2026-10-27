"""SSE evidence reader for the real HTTP chat tests; no provider calls or waits."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StreamResult:
    frames: list[dict[str, Any]]
    deltas_text: str
    # The complete final envelope, including nonzero error frames, for callers to assert.
    final: dict[str, Any] | None
    session_id: str | None
    message_id: str | None
    done: bool


def read_stream(response_lines: Iterable[str | bytes]) -> StreamResult:
    """Consume ``httpx.Response.iter_lines()``; retain explicit final/DONE evidence."""
    frames: list[dict[str, Any]] = []
    deltas: list[str] = []
    pending: list[str] = []
    final: dict[str, Any] | None = None
    session_id = message_id = None
    done = False

    def flush() -> None:
        nonlocal final, session_id, message_id, done
        payload = "\n".join(pending)
        pending.clear()
        if not payload:
            return
        if payload.strip() == "[DONE]":
            done = True
            return
        try:
            frame = json.loads(payload)
        except json.JSONDecodeError:
            return
        if not isinstance(frame, dict) or not isinstance(frame.get("data"), dict):
            return
        frames.append(frame)
        data = frame["data"]
        if isinstance(data.get("session_id"), str) and data["session_id"]:
            session_id = data["session_id"]
        if isinstance(data.get("message_id"), str) and data["message_id"]:
            message_id = data["message_id"]
        if data.get("final") is True:
            final = frame
        elif frame.get("code") == 0 and isinstance(data.get("answer"), str):
            deltas.append(data["answer"])

    for raw in response_lines:
        line = (raw.decode("utf-8") if isinstance(raw, bytes) else raw).rstrip("\r\n")
        if line == "":
            flush()
            if done:
                break
        elif line.startswith("data:"):
            value = line[5:]
            pending.append(value[1:] if value.startswith(" ") else value)
    if not done:
        flush()
    return StreamResult(frames, "".join(deltas), final, session_id, message_id, done)
