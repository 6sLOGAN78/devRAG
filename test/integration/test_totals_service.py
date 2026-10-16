"""settle_totals sets document and dataset counters to the truth of the index (plan 04-10, KB-19, R-159)."""
from __future__ import annotations

import uuid

import pytest

from api.db.services.totals_service import settle_totals
from common.doc_store.doc_store_base import index_name
from rag.utils.es_conn import get_doc_store
from test.helpers.doc_store_contract import row
from test.helpers.uploads import sql, text_bytes
from test.integration import test_upload_service as base
from test.integration.test_document_service import doc_rows  # noqa: F401

pytestmark = pytest.mark.integration

_bound_database = base._bound_database
settings = base.settings
llm = base.llm
registry = base.registry
storage = base.storage
space = base.space
item = base.item
upload = base.upload


def index_chunks(cfg, owner, dataset, doc_id: str, count: int, tokens: int = 10) -> None:
    rows = []
    for i in range(count):
        r = row(uuid.uuid4().hex, doc_id, f"chunk {i}", i % 8, i)
        r["token_num_int"] = tokens
        rows.append(r)
    assert get_doc_store(cfg).insert(rows, index_name(owner.tenant_id), dataset.id) == []


def counters(doc_id: str, dataset_id: str):
    d = sql("SELECT `chunk_num`, `token_num` FROM `document` WHERE `id` = %s", (doc_id,))[0]
    k = sql("SELECT `chunk_num`, `token_num` FROM `knowledgebase` WHERE `id` = %s", (dataset_id,))[0]
    return tuple(map(int, d)), tuple(map(int, k))


def test_settle_sets_the_truth_and_moves_the_dataset_by_the_difference(settings, space, storage):
    owner, dataset = space
    a = upload(settings, owner, dataset, [item("a.txt", text_bytes("a"))], storage=storage)[0]
    b = upload(settings, owner, dataset, [item("b.txt", text_bytes("b"))], storage=storage)[0]
    sql("UPDATE `document` SET `chunk_num` = 99, `token_num` = 999 WHERE `id` = %s", (a["id"],))
    sql("UPDATE `document` SET `chunk_num` = 7, `token_num` = 70 WHERE `id` = %s", (b["id"],))
    sql("UPDATE `knowledgebase` SET `chunk_num` = 106, `token_num` = 1069 WHERE `id` = %s", (dataset.id,))
    index_chunks(settings, owner, dataset, a["id"], 5)

    assert settle_totals(settings, owner.tenant_id, dataset.id, a["id"]) == (5, 50)
    assert counters(a["id"], dataset.id) == ((5, 50), (12, 120))
    assert counters(b["id"], dataset.id)[0] == (7, 70)
    # idempotent
    assert settle_totals(settings, owner.tenant_id, dataset.id, a["id"]) == (5, 50)
    assert counters(a["id"], dataset.id) == ((5, 50), (12, 120))


def test_settle_with_no_chunks_sets_zero_and_never_goes_negative(settings, space, storage):
    owner, dataset = space
    a = upload(settings, owner, dataset, [item("a.txt", text_bytes("a"))], storage=storage)[0]
    sql("UPDATE `document` SET `chunk_num` = 4, `token_num` = 40 WHERE `id` = %s", (a["id"],))
    sql("UPDATE `knowledgebase` SET `chunk_num` = 1, `token_num` = 1 WHERE `id` = %s", (dataset.id,))
    assert settle_totals(settings, owner.tenant_id, dataset.id, a["id"]) == (0, 0)
    assert counters(a["id"], dataset.id) == ((0, 0), (0, 0))
