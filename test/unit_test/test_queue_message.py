"""Queue message codec and naming (plan 04-07, ING-02, T-04-07-01)."""
from __future__ import annotations

import json

import pytest

from rag.queue.queue_base import MessageMalformed, QueueMessage, decode_message, encode_message, queue_name

pytestmark = pytest.mark.unit

TASK = "a" * 32


def test_round_trip():
    fields = encode_message(TASK, "dig")
    assert set(fields) == {"message"}
    assert decode_message(fields) == (TASK, "dig")


def test_queue_name():
    assert queue_name("te", 1) == "te.1.common"
    assert queue_name("te", 0) == "te.0.common"


@pytest.mark.parametrize(
    "fields",
    [
        {"message": "not json"},
        {"message": json.dumps({"digest": "d"})},
        {"message": json.dumps({"task_id": "xyz", "digest": "d"})},
        {"message": json.dumps({"task_id": TASK, "digest": "d", "extra": 1})},
        {"message": json.dumps(["list"])},
        {},
    ],
)
def test_malformed_bodies_are_rejected(fields):
    with pytest.raises(MessageMalformed):
        decode_message(fields)


def test_message_is_frozen():
    msg = QueueMessage(queue="q", message_id="1-0", task_id=TASK, digest="d", delivered=1)
    with pytest.raises(AttributeError):
        msg.task_id = "x"  # type: ignore[misc]
