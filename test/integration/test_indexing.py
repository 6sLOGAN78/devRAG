"""One task end to end against the real MySQL, MinIO and Elasticsearch, with a loopback embedding provider (plan 04-11).

ING-09, ING-13..15, CHUNK-16, IDX-01..03, IDX-07, DOC-20. The loopback provider is the other end of the wire, never a stub of devRag code.
"""

from __future__ import annotations

import collections
import math
import re
import threading
from collections.abc import Iterator

import pytest

from api.db.database import DB
from api.db.services import task_service
from test.helpers.accounts import AccountRegistry
from test.helpers.fake_provider import FakeProvider, running_fake_provider
from test.helpers.ingest import (
    DIMENSION,
    World,
    add_document,
    add_task,
    cleanup_tasks,
    indexed,
    make_pipeline_world,
    paragraphs,
    progress_msg,
    run_task,
    text_pdf,
    thirteen_page_pdf,
)
from test.helpers.uploads import sql
from test.integration.test_upload_service import _bound_database  # noqa: F401  (autouse module fixture)
from test.testcases.conftest import BASE_URL

pytestmark = pytest.mark.integration


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


def embed_sizes(fake: FakeProvider) -> list[int]:
    return [len(r.body["input"]) for r in fake.hits("/v1/embeddings")]


def norm(vector: list[float]) -> float:
    return math.sqrt(sum(x * x for x in vector))


def test_a_text_file_becomes_forty_normalised_chunks(world, fake):
    doc = add_document(world, "forty.txt", paragraphs(40))
    task = add_task(doc)
    result = run_task(world, task, deps=world.deps(ingest={"batch_size": 8}))

    chunks = sorted(indexed(world, doc_id=[doc]), key=lambda h: h["order_int"])
    assert [h["id"] for h in chunks] == [f"{doc}_{i}" for i in range(40)]
    assert result.chunk_count == 40 and sorted(result.chunk_ids) == sorted(h["id"] for h in chunks)
    for i, h in enumerate(chunks):
        vec = h[f"q_{DIMENSION}_vec"]
        assert len(vec) == DIMENSION and abs(norm(vec) - 1.0) < 1e-6
        assert h["order_int"] == i and h["task_id"] == task and h["origin_kwd"] == "parsed" and h["doc_enabled_int"] == 1
        assert h["available_int"] == 1 and h["docnm_kwd"] == "forty.txt" and h["kb_id"] == world.dataset.id
    sizes = embed_sizes(fake)
    histogram = collections.Counter(sizes)
    print("embedding request sizes:", dict(histogram))
    assert len(sizes) >= 3 and max(sizes) <= 16


def test_a_rerun_writes_the_same_ids_and_a_shorter_rerun_leaves_no_surplus(world):
    doc = add_document(world, "again.txt", paragraphs(40))
    task = add_task(doc)
    run_task(world, task)
    run_task(world, task)
    assert len(indexed(world, doc_id=[doc])) == 40

    sql("UPDATE `document` SET `parser_config` = %s WHERE `id` = %s", ('{"chunk_token_num": 1000}', doc))
    result = run_task(world, task)
    assert result.chunk_count == 14
    assert sorted(h["id"] for h in indexed(world, doc_id=[doc])) == sorted(f"{doc}_{i}" for i in range(14))


def test_a_single_task_text_file_is_not_capped_at_one_thousand_chunks(world):
    doc = add_document(world, "many.txt", paragraphs(1600, tokens=8), {"chunk_token_num": 12})
    task = add_task(doc, 0, 1000000)
    result = run_task(world, task)
    assert result.chunk_count == 1600
    assert len(indexed(world, doc_id=[doc])) == 1600
    assert {f"{doc}_0", f"{doc}_1599"} <= set(result.chunk_ids)


def test_a_pdf_in_two_tasks_uses_page_based_ids_and_one_thumbnail(world):
    doc = add_document(world, "thirteen.pdf", thirteen_page_pdf())
    first, second = add_task(doc, 0, 12), add_task(doc, 12, 13)
    run_task(world, first)
    thumb = sql("SELECT `thumbnail` FROM `document` WHERE `id` = %s", (doc,))[0][0]
    assert thumb.startswith("data:image/jpeg;base64,") and len(thumb) <= 16384

    result = run_task(world, second)
    assert sql("SELECT `thumbnail` FROM `document` WHERE `id` = %s", (doc,))[0][0] == thumb
    late = indexed(world, task_id=[second])
    assert result.chunk_count == len(late) >= 1
    assert all(re.fullmatch(rf"{doc}_12\d{{3}}", h["id"]) for h in late)
    assert all(h["page_num_int"] == [13] and h["position_int"][0][0] == 13 and h["page_dims_flt"] for h in late)
    early = indexed(world, task_id=[first])
    assert early and all(re.fullmatch(rf"{doc}_\d{{1,3}}", h["id"]) for h in early)
    assert {p for h in early for p in h["page_num_int"]} == set(range(1, 13))


def test_a_document_switched_off_stores_disabled_chunks(world):
    doc = add_document(world, "off.txt", paragraphs(3))
    sql("UPDATE `document` SET `status` = '0' WHERE `id` = %s", (doc,))
    run_task(world, add_task(doc))
    assert {h["doc_enabled_int"] for h in indexed(world, doc_id=[doc])} == {0}


def test_a_pdf_without_text_makes_no_chunks_and_says_so(world):
    doc = add_document(world, "blank.pdf", text_pdf([None, None, None]))
    task = add_task(doc, 0, 3)
    result = run_task(world, task)
    assert result.chunk_count == 0 and result.pages_total == 3 and result.pages_without_text == 3
    assert "3 of 3 pages in this range had no readable text" in progress_msg(task)
    assert indexed(world, doc_id=[doc]) == []


def test_progress_grows_and_stays_below_one_with_clean_lines(world):
    doc = add_document(world, "lines.txt", paragraphs(40))
    task = add_task(doc)
    run_task(world, task, deps=world.deps(ingest={"batch_size": 8}))
    value = sql("SELECT `progress` FROM `task` WHERE `id` = %s", (task,))[0][0]
    assert 0.1 <= value < 1
    message = progress_msg(task)
    done = [int(m) for m in re.findall(r"Indexed (\d+) of 40 chunks", message)]
    assert done == sorted(done) and done[-1] == 40
    assert "/" not in message.replace("//", "") and "Traceback" not in message and "sk-" not in message
    assert not message.count("http")


def test_the_database_connection_is_closed_while_the_provider_is_called(world, monkeypatch):
    import rag.svr.embedding as embedding

    seen: list[bool] = []
    threads: list[str] = []
    real = embedding.LLMBundle

    class Watching(real):
        def encode(self, texts):
            seen.append(DB.is_closed())
            threads.append(threading.current_thread().name)
            return super().encode(texts)

    monkeypatch.setattr(embedding, "LLMBundle", Watching)
    doc = add_document(world, "conn.txt", paragraphs(5))
    run_task(world, add_task(doc))
    assert seen and all(seen)
    assert all(name.startswith("embed") for name in threads)
    assert task_service.task_is_current(sql("SELECT `id` FROM `task` WHERE `doc_id` = %s", (doc,))[0][0])
