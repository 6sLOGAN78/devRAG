from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from api.db.services.service_errors import Kind, ServiceError
from api.utils import reasons
from common.doc_store.doc_store_base import DimensionConflict, DocStoreError
from common.ingest_codes import FAILURE_CODES, is_terminal
from rag.chunking.factory import ChunkerUnavailable
from rag.parsers.errors import ArchiveLimitsExceeded, FileDamaged, FileTooLarge, NoReadableText, UnsupportedType
from rag.svr.control import LockLost, TaskCancelled, TaskControl, wait_for
from rag.svr.failure import PLAIN_MESSAGES, TaskFailure, classify, format_failure_line, parse_failure_line
from rag.utils.storage_base import StorageError, StorageNotFound

pytestmark = pytest.mark.unit


def svc(reason: str, message: str = "x") -> ServiceError:
    return ServiceError(Kind.INVALID, reason, message)


@pytest.mark.parametrize(
    ("exc", "step", "code"),
    [
        (FileDamaged(), "parse", "file_damaged"),
        (NoReadableText(), "parse", "no_readable_text"),
        (UnsupportedType(), "parse", "unsupported_type"),
        (FileTooLarge(), "parse", "file_too_large"),
        (ArchiveLimitsExceeded(), "parse", "archive_limits_exceeded"),
        (ChunkerUnavailable(), "chunk", "chunker_unavailable"),
        (svc(reasons.PROVIDER_TIMEOUT), "embed", "provider_timeout"),
        (svc(reasons.PROVIDER_RATE_LIMITED), "embed", "provider_rate_limited"),
        (svc(reasons.PROVIDER_UNREACHABLE), "embed", "provider_unreachable"),
        (svc(reasons.MODEL_UNAVAILABLE), "embed", "model_unavailable"),
        (svc(reasons.DIMENSION_MISMATCH), "embed", "dimension_mismatch"),
        (StorageError("boom"), "fetch", "storage_unavailable"),
        (StorageNotFound("gone"), "fetch", "storage_unavailable"),
        (DocStoreError("down"), "index", "index_unavailable"),
        (DimensionConflict("dims"), "index", "dimension_mismatch"),
    ],
)
def test_classify_maps_each_exception(exc, step, code):
    failure = classify(exc, step)
    assert (failure.step, failure.code) == (step, code)
    assert failure.terminal == is_terminal(code)
    assert failure.message == PLAIN_MESSAGES[code]


def test_provider_refused_is_terminal_with_a_cut_detail():
    failure = classify(svc(reasons.PROVIDER_REFUSED, "n" * 500), "embed")
    assert failure.code == "provider_refused" and failure.terminal
    assert 0 < len(failure.detail) <= 300


def test_unknown_exception_is_unexpected_and_hides_the_class_name():
    failure = classify(ZeroDivisionError("secret /etc/passwd"), "index")
    assert failure.code == "unexpected" and not failure.terminal
    assert failure.message == "Parsing failed for an unexpected reason."
    assert "ZeroDivision" not in failure.message + failure.detail and "/etc" not in failure.message + failure.detail


def test_task_failure_passes_through():
    original = TaskFailure("parse", "too_many_chunks")
    assert classify(original, "embed") is original


def test_every_failure_code_has_a_plain_message():
    assert set(FAILURE_CODES) <= set(PLAIN_MESSAGES)
    assert PLAIN_MESSAGES["too_many_chunks"] == "This document produced more chunks than one parsing task can store."


def test_failure_line_round_trip_finds_the_last_line():
    line = format_failure_line("embed", "provider_timeout", "The embedding provider timed out.")
    assert line == "[failed] step=embed code=provider_timeout message=The embedding provider timed out."
    progress = f"10:00:00  Indexed 3 of 9 chunks.\n10:00:01  [failed] step=fetch code=storage_unavailable message=x\n10:00:02  {line}"
    info = parse_failure_line(progress)
    assert (info.step, info.code, info.message) == ("embed", "provider_timeout", "The embedding provider timed out.")
    assert parse_failure_line("10:00:00  Indexed 3 of 9 chunks.") is None


def test_detail_is_redacted():
    failure = TaskFailure("embed", "provider_refused", detail="refused sk-" + "a" * 24 + " please")
    assert "sk-" not in failure.detail


@pytest.mark.parametrize("message", ["see /etc/x", "C:\\temp\\x", "Traceback (most recent call last)", 'File "a.py"'])
def test_message_with_internal_detail_is_refused(message):
    with pytest.raises(ValueError):
        TaskFailure("parse", "file_damaged", message)


def test_control_check_distinguishes_cancel_and_lost():
    control = TaskControl()
    control.check()
    control.cancel.set()
    with pytest.raises(TaskCancelled):
        control.check()
    other = TaskControl()
    other.lost.set()
    with pytest.raises(LockLost):
        other.check()
    assert not issubclass(LockLost, TaskCancelled) and not issubclass(TaskCancelled, LockLost)


def test_wait_for_returns_the_result_and_raises_on_cancel_without_waiting():
    control = TaskControl()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert wait_for(pool.submit(lambda: 7), control) == 7
        gate = threading.Event()
        future = pool.submit(gate.wait, 5)
        threading.Timer(0.1, control.cancel.set).start()
        started = time.monotonic()
        with pytest.raises(TaskCancelled):
            wait_for(future, control)
        assert time.monotonic() - started < 1.0
        gate.set()
