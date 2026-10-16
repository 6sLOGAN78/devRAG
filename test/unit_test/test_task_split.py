"""Page-range splitting and the task digest (plan 04-10, ING-01, D-05)."""
from __future__ import annotations

import re

import pytest

from api.db.services.task_service import split_pages, task_digest
from common import ingest_codes as c


@pytest.mark.parametrize(
    ("total", "size", "expected"),
    [
        (13, 12, [(0, 12), (12, 13)]),
        (12, 12, [(0, 12)]),
        (1, 12, [(0, 1)]),
        (None, 12, [(0, 1000000)]),
        (0, 12, [(0, 1000000)]),
        (25, 12, [(0, 12), (12, 24), (24, 25)]),
    ],
)
def test_split_pages(total, size, expected):
    assert split_pages(total, size) == expected


BASE = ("d" * 32, 0, 12, "h" * 32, "naive", 512, "\n", 0)


def test_digest_is_stable_16_hex():
    one = task_digest(*BASE)
    assert one == task_digest(*BASE)
    assert re.fullmatch(r"[0-9a-f]{16}", one)


@pytest.mark.parametrize("index", range(8))
def test_every_input_changes_the_digest(index):
    changed = list(BASE)
    changed[index] = {0: "e" * 32, 1: 1, 2: 13, 3: "i" * 32, 4: "qa", 5: 256, 6: "!", 7: 10}[index]
    assert task_digest(*changed) != task_digest(*BASE)


def test_queue_unavailable_is_a_failure_code_but_not_terminal():
    assert "queue_unavailable" in c.FAILURE_CODES
    assert not c.is_terminal("queue_unavailable")
    assert (c.LOG_RUNNING, c.LOG_DONE, c.LOG_FAILED, c.LOG_CANCELLED) == ("running", "done", "failed", "cancelled")
