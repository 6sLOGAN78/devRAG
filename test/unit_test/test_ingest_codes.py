from __future__ import annotations

import pytest

from api.db.services.knowledgebase_service import PARSER_IDS
from api.utils import reasons
from common import ingest_codes as c

pytestmark = pytest.mark.unit

UI_FAILURE_CODES = (
    "no_readable_text unsupported_type chunker_unavailable file_damaged file_too_large archive_limits_exceeded "
    "provider_timeout provider_rate_limited provider_unreachable provider_refused model_unavailable "
    "dimension_mismatch index_unavailable storage_unavailable worker_lost document_deleted"
).split()


def test_run_codes():
    assert (c.RUN_NOT_STARTED, c.RUN_RUNNING, c.RUN_CANCELLED, c.RUN_DONE, c.RUN_FAILED) == ("0", "1", "2", "3", "4")


def test_steps():
    assert c.STEPS == ("queue", "fetch", "parse", "chunk", "embed", "index")


def test_failure_codes_cover_ui_spec():
    assert set(UI_FAILURE_CODES) <= set(c.FAILURE_CODES)


def test_terminal_codes_exclude_retryable():
    retryable = {"file_damaged", "provider_timeout", "provider_rate_limited", "provider_unreachable", "index_unavailable", "storage_unavailable", "worker_lost"}
    assert not (retryable & c.TERMINAL_CODES)
    assert c.TERMINAL_CODES <= set(c.FAILURE_CODES)
    assert c.is_terminal("no_readable_text")
    assert not c.is_terminal("worker_lost")


def test_methods():
    assert c.METHOD_ORDER == ("naive", "qa", "paper", "book", "laws", "presentation", "table", "manual", "resume", "picture", "email", "tag", "one", "audio")
    assert c.IMPLEMENTED_PARSERS == frozenset({"naive", "one", "manual", "qa", "book", "paper", "laws", "presentation"})
    assert set(c.METHOD_ORDER) <= set(PARSER_IDS)


@pytest.mark.parametrize(
    "name",
    ["PARSE_UNAVAILABLE", "CHUNKER_UNAVAILABLE", "ALREADY_RUNNING", "QUEUE_UNAVAILABLE", "PARSE_RUNNING", "PARSER_CONFIG_INVALID", "CHUNK_TOO_LONG", "CONFIRM_REQUIRED", "NOT_RUNNING"],
)
def test_new_reasons(name):
    assert getattr(reasons, name) == name.lower()
