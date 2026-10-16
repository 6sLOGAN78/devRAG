"""Cancel, stale worker, deleted document and every failure class against the real stack (plan 04-11; ING-12, IDX-07, D-06, D-08, R-155, R-158).

Timing is driven only by the loopback provider's ``delay_ms`` and ``TaskControl`` events set from a test thread; nothing in product code is a test hook.
"""

from __future__ import annotations

import dataclasses
import logging
import tempfile
import threading
import time
from collections.abc import Iterator

import pytest

from api.db.services.task_service import load_task_context
from rag.svr.control import TaskCancelled, TaskControl
from rag.svr.failure import TaskFailure
from test.helpers.accounts import AccountRegistry
from test.helpers.fake_provider import FakeProvider, running_fake_provider
from test.helpers.ingest import (
    World,
    add_document,
    add_task,
    cleanup_tasks,
    garbage_bytes,
    indexed,
    make_docx,
    make_pipeline_world,
    paragraphs,
    progress_msg,
    run_task,
    truncated,
)
from test.helpers.uploads import sql
from test.helpers.wait import wait_until
from test.integration.test_upload_service import _bound_database  # noqa: F401  (autouse module fixture)
from test.testcases.conftest import BASE_URL

pytestmark = pytest.mark.integration

_STANDARD = set(vars(logging.makeLogRecord({})))


@pytest.fixture
def registry() -> Iterator[AccountRegistry]:
    accounts = AccountRegistry(BASE_URL)
    try:
        yield accounts
    finally:
        cleanup_tasks(accounts)
        accounts.cleanup()


@pytest.fixture
def fake() -> Iterator[FakeProvider]:
    with running_fake_provider() as provider:
        yield provider


@pytest.fixture
def world(registry, fake) -> World:
    return make_pipeline_world(registry, fake)


def fails(world: World, task: str, caplog: pytest.LogCaptureFixture, deps=None) -> TaskFailure:
    caplog.set_level(logging.INFO)
    with pytest.raises(TaskFailure) as err:
        run_task(world, task, deps=deps)
    assert_clean(world, task, caplog, err.value)
    return err.value


def assert_clean(world: World, task: str, caplog: pytest.LogCaptureFixture, failure: TaskFailure | None) -> None:
    """No path, key, trace or provider address in the failure line, the progress text or any log record of the run."""
    ctx = load_task_context(task)
    forbidden = [tempfile.gettempdir(), "ingest-", "Traceback", world.api_key, f"127.0.0.1:{world.fake.port}", "http://", "https://"]
    if ctx is not None:
        forbidden.append(ctx.doc_location)
    texts = [progress_msg(task)]
    if failure is not None:
        texts += [failure.line(), failure.message, failure.detail]
    for record in caplog.records:
        if not record.name.startswith(("rag.", "api.", "common.")):
            continue  # third-party transport loggers are not ours; their level is set by deployment logging config
        extras = {k: v for k, v in vars(record).items() if k not in _STANDARD}
        texts += [record.getMessage(), str(record.exc_text or ""), repr(extras)]
    for text in texts:
        for needle in forbidden:
            assert needle not in text, needle


def first_batch_indexed(world: World, doc: str, count: int) -> bool:
    return len(indexed(world, doc_id=[doc])) >= count


def run_with_signal(world: World, task: str, doc: str, signal, batch: int = 8):
    """Run the pipeline on this thread; a watcher fires ``signal`` once the first batch is in the index. Returns (error, signalled_at, stopped_at)."""
    control = TaskControl()
    fired: list[float] = []

    def watch() -> None:
        wait_until(lambda: first_batch_indexed(world, doc, batch), timeout=30, interval=0.05)
        signal(control)
        fired.append(time.monotonic())

    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    error: BaseException | None = None
    try:
        run_task(world, task, control, world.deps(ingest={"batch_size": batch}))
    except BaseException as exc:  # noqa: BLE001 - the test inspects it
        error = exc
    stopped = time.monotonic()
    watcher.join(10)
    return error, (fired[0] if fired else None), stopped


# ----------------------------------------------------------------------------- cancel and stale worker


def test_cancel_in_the_middle_of_an_embedding_call_is_noticed_within_1_5_seconds(world, fake):
    fake.delay_ms = 1500
    doc = add_document(world, "cancel.txt", paragraphs(40))
    task = add_task(doc)
    error, fired, stopped = run_with_signal(world, task, doc, lambda c: c.cancel.set())
    assert isinstance(error, TaskCancelled)
    assert fired is not None
    elapsed = stopped - fired
    assert elapsed <= 1.5, elapsed
    assert len(indexed(world, doc_id=[doc])) == 8, "the first batch is kept and no later batch was written"


def test_a_vanished_task_row_removes_the_chunks_of_that_task(world, fake):
    fake.delay_ms = 400
    doc = add_document(world, "stale.txt", paragraphs(40))
    task = add_task(doc)
    error, _, _ = run_with_signal(world, task, doc, lambda c: sql("DELETE FROM `task` WHERE `id` = %s", (task,)))
    assert isinstance(error, TaskCancelled)
    assert indexed(world, task_id=[task]) == []


def test_a_document_no_longer_running_stops_the_task_and_removes_its_chunks(world, fake):
    fake.delay_ms = 300
    doc = add_document(world, "rerun.txt", paragraphs(40))
    task = add_task(doc)
    error, _, _ = run_with_signal(world, task, doc, lambda c: sql("UPDATE `document` SET `run` = '2' WHERE `id` = %s", (doc,)))
    assert isinstance(error, TaskCancelled)
    assert indexed(world, task_id=[task]) == []


def test_a_deleted_document_leaves_no_orphan_chunk(world, fake):
    fake.delay_ms = 300
    doc = add_document(world, "gone.txt", paragraphs(40))
    task = add_task(doc)

    def remove(_control: TaskControl) -> None:
        sql("DELETE FROM `task` WHERE `doc_id` = %s", (doc,))
        sql("DELETE FROM `document` WHERE `id` = %s", (doc,))

    error, _, _ = run_with_signal(world, task, doc, remove)
    assert isinstance(error, TaskCancelled)
    assert indexed(world, doc_id=[doc]) == []


# ----------------------------------------------------------------------------- terminal failures


def test_a_chunking_method_that_is_not_built_is_terminal(world, caplog):
    doc = add_document(world, "qa.txt", paragraphs(3))
    sql("UPDATE `document` SET `parser_id` = 'qa' WHERE `id` = %s", (doc,))
    failure = fails(world, add_task(doc), caplog)
    assert (failure.code, failure.terminal) == ("chunker_unavailable", True)
    assert indexed(world, doc_id=[doc]) == []


def test_vectors_of_another_size_are_terminal_before_any_insert(world, fake, caplog):
    fake.embedding_dim = 16
    doc = add_document(world, "dim.txt", paragraphs(5))
    failure = fails(world, add_task(doc), caplog)
    assert (failure.code, failure.terminal) == ("dimension_mismatch", True)
    assert indexed(world, doc_id=[doc]) == []


def test_a_refusing_provider_is_terminal_with_a_short_detail(registry, fake, caplog):
    world = make_pipeline_world(registry, fake, embedding_model="fake-filter")
    doc = add_document(world, "refuse.txt", paragraphs(3))
    failure = fails(world, add_task(doc), caplog)
    assert (failure.code, failure.terminal) == ("provider_refused", True)
    assert 0 < len(failure.detail) <= 300
    assert indexed(world, doc_id=[doc]) == []


# ----------------------------------------------------------------------------- retryable failures


def test_garbage_bytes_in_a_pdf_are_a_retryable_damaged_file(world, caplog):
    doc = add_document(world, "bad.pdf", b"%PDF-1.4\n" + garbage_bytes())
    failure = fails(world, add_task(doc), caplog)
    assert (failure.step, failure.code, failure.terminal) == ("parse", "file_damaged", False)


def test_a_truncated_docx_is_a_retryable_damaged_file(world, caplog):
    doc = add_document(world, "cut.docx", truncated(make_docx(paragraphs=["hello there"] * 20)))
    failure = fails(world, add_task(doc), caplog)
    assert (failure.code, failure.terminal) == ("file_damaged", False)


def test_a_provider_that_does_not_answer_is_a_retryable_timeout(registry, fake, caplog):
    world = make_pipeline_world(registry, fake, embedding_model="fake-timeout")
    doc = add_document(world, "slow.txt", paragraphs(3))
    failure = fails(world, add_task(doc), caplog)
    assert (failure.step, failure.code, failure.terminal) == ("embed", "provider_timeout", False)


def test_an_unreachable_index_is_a_retryable_index_failure(world, caplog):
    doc = add_document(world, "idx.txt", paragraphs(3))
    task = add_task(doc)
    broken = dataclasses.replace(world.settings, es=dataclasses.replace(world.settings.es, hosts="http://127.0.0.1:1"))
    failure = fails(world, task, caplog, deps=world.deps(settings=broken))
    assert (failure.step, failure.code, failure.terminal) == ("index", "index_unavailable", False)


def test_the_failure_line_is_the_last_line_and_parses_back(world, caplog):
    from api.db.services.task_service import mark_task_failed
    from rag.svr.failure import parse_failure_line

    doc = add_document(world, "line.txt", paragraphs(2))
    sql("UPDATE `document` SET `parser_id` = 'qa' WHERE `id` = %s", (doc,))
    task = add_task(doc)
    failure = fails(world, task, caplog)
    mark_task_failed(task, failure.line())
    info = parse_failure_line(progress_msg(task))
    assert info is not None and (info.step, info.code) == (failure.step, failure.code)
    assert_clean(world, task, caplog, failure)
