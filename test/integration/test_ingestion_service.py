"""Start, cancel and re-parse against the real MySQL, Elasticsearch, MinIO and Valkey (plan 04-10; ING-01, ING-12, DOC-09..11, D-01..D-04, D-06, D-09).

Every test uses its own queue prefix and consumer group, so the running executor never sees these messages; the fixture removes the stream keys
it made and asserts none are left.
"""

from __future__ import annotations

import dataclasses
import json
import secrets
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
import valkey

from api.db.database import DB
from api.db.models import PipelineOperationLog
from api.db.services import ingestion_service as ing
from api.db.services.auth_service import AUTH_API, Principal
from api.db.services.service_errors import Kind
from common.doc_store.doc_store_base import index_name
from rag.queue.queue_base import QueueUnavailable
from rag.utils.es_conn import get_doc_store
from test.helpers.accounts import AccountRegistry
from test.helpers.doc_store_contract import row
from test.helpers.pdf_files import garbage_bytes, thirteen_page_pdf
from test.helpers.uploads import sql, text_bytes
from test.integration import test_upload_service as base
from test.integration.test_document_service import chunk_ids, team_dataset_of
from test.integration.test_knowledgebase_service import configure, join, principal_of
from test.testcases.conftest import BASE_URL

pytestmark = pytest.mark.integration

_bound_database = base._bound_database
storage = base.storage
space = base.space
item = base.item
upload = base.upload
refused = base.refused



@pytest.fixture
def settings() -> Iterator[Any]:
    cfg = base.load_settings()
    prefix = f"tq{secrets.token_hex(6)}"
    cfg = dataclasses.replace(cfg, ingest=dataclasses.replace(cfg.ingest, queue_prefix=prefix, consumer_group=f"g{secrets.token_hex(4)}"))
    yield cfg
    rd = cfg.redis
    raw = valkey.Valkey(host=rd.host, port=rd.port, password=rd.password or None, db=rd.db, decode_responses=True)
    try:
        for key in raw.scan_iter(match=prefix + "*"):
            raw.delete(key)
        assert list(raw.scan_iter(match=prefix + "*")) == []
    finally:
        raw.close()
    from rag.queue.factory import reset_queue_cache

    reset_queue_cache()


@pytest.fixture
def llm(settings):
    """The upload tests' module-scoped ``llm`` depends on a module-scoped settings; this module's settings carry a per-test queue prefix."""
    return dataclasses.replace(settings.llm, encryption_key=base.urlsafe_b64encode(base.os.urandom(32)).decode(), key_id="k1")


@pytest.fixture
def registry() -> Iterator[AccountRegistry]:
    """Like the upload tests' registry, and it also removes the task and log rows of the accounts' documents (account cleanup does not)."""
    accounts = AccountRegistry(BASE_URL)
    try:
        yield accounts
    finally:
        for acc in accounts.created:
            sql("DELETE FROM `task` WHERE `doc_id` IN (SELECT `id` FROM `document` WHERE `kb_id` IN (SELECT `id` FROM `knowledgebase` WHERE `tenant_id` = %s))", (acc.tenant_id,))
            sql("DELETE FROM `pipeline_operation_log` WHERE `tenant_id` = %s", (acc.tenant_id,))
        accounts.cleanup()


def stream(cfg) -> list[dict]:
    rd = cfg.redis
    raw = valkey.Valkey(host=rd.host, port=rd.port, password=rd.password or None, db=rd.db, decode_responses=True)
    try:
        entries = raw.xrange(f"{cfg.ingest.queue_prefix}.0.common")
    finally:
        raw.close()
    return [json.loads(fields["message"]) for _, fields in entries]


def start(cfg, who, dataset, ids, confirm=False, **kw):
    visible = ing.authorize_parse(principal_of(who), dataset.id)
    return ing.start_parse(cfg, visible, principal_of(who), ids, confirm, **kw)


def tasks(doc_id: str) -> list[tuple[int, int]]:
    return [(int(a), int(b)) for a, b in sql("SELECT `from_page`, `to_page` FROM `task` WHERE `doc_id` = %s ORDER BY `from_page`", (doc_id,))]


def doc_state(doc_id: str) -> tuple:
    return sql("SELECT `run`, `progress`, `chunk_num`, `token_num` FROM `document` WHERE `id` = %s", (doc_id,))[0]


def logs(doc_id: str) -> list[str]:
    return [r[0] for r in sql("SELECT `operation_status` FROM `pipeline_operation_log` WHERE `document_id` = %s ORDER BY `create_time`, `id`", (doc_id,))]


def index_chunks(cfg, owner, dataset, doc_id: str, plain: int = 0, edited: int = 0, manual: int = 0) -> list[str]:
    rows = []
    for origin, count in ((None, plain), ("edited", edited), ("manual", manual)):
        for i in range(count):
            r = row(uuid.uuid4().hex, doc_id, f"{origin} chunk {i}", i % 8, i)
            r["token_num_int"] = 10
            if origin:
                r["origin_kwd"] = origin
            rows.append(r)
    assert get_doc_store(cfg).insert(rows, index_name(owner.tenant_id), dataset.id) == []
    sql("UPDATE `document` SET `chunk_num` = %s, `token_num` = %s WHERE `id` = %s", (len(rows), len(rows) * 10, doc_id))
    sql("UPDATE `knowledgebase` SET `chunk_num` = `chunk_num` + %s, `token_num` = `token_num` + %s WHERE `id` = %s", (len(rows), len(rows) * 10, dataset.id))
    return [r["id"] for r in rows]


def one_doc(cfg, owner, dataset, storage, name="a.txt", data=None):
    return upload(cfg, owner, dataset, [item(name, data if data is not None else text_bytes(name))], storage=storage)[0]


def dataset_chunks(dataset_id: str) -> int:
    return int(sql("SELECT `chunk_num` FROM `knowledgebase` WHERE `id` = %s", (dataset_id,))[0][0])


# ----------------------------------------------------------------------------- start


def test_upload_never_enqueues_and_start_creates_one_task_and_one_message(settings, space, storage):
    owner, dataset = space
    doc = one_doc(settings, owner, dataset, storage)
    assert doc["run"] == "0" and tasks(doc["id"]) == [] and stream(settings) == []

    started = start(settings, owner, dataset, [doc["id"]])
    assert [(s.doc_id, s.task_count) for s in started] == [(doc["id"], 1)]
    assert tasks(doc["id"]) == [(0, 1000000)]
    assert doc_state(doc["id"])[:2] == ("1", 0.0)
    assert logs(doc["id"]) == ["running"]
    task_id, digest = sql("SELECT `id`, `digest` FROM `task` WHERE `doc_id` = %s", (doc["id"],))[0]
    assert stream(settings) == [{"task_id": task_id, "digest": digest}] and len(digest) == 16


def test_a_thirteen_page_pdf_becomes_two_tasks(settings, space, storage):
    owner, dataset = space
    doc = one_doc(settings, owner, dataset, storage, "big.pdf", thirteen_page_pdf())
    assert start(settings, owner, dataset, [doc["id"]])[0].task_count == 2
    assert tasks(doc["id"]) == [(0, 12), (12, 13)]
    assert len(stream(settings)) == 2


def test_a_damaged_pdf_gets_one_full_range_task(settings, space, storage):
    owner, dataset = space
    doc = one_doc(settings, owner, dataset, storage, "bad.pdf", b"%PDF-1.4\n" + garbage_bytes())
    start(settings, owner, dataset, [doc["id"]])
    assert tasks(doc["id"]) == [(0, 1000000)]
    assert storage.open_streams == 0


# ----------------------------------------------------------------------------- confirmation


def test_a_finished_document_needs_confirmation_and_nothing_changes(settings, space, storage):
    owner, dataset = space
    doc = one_doc(settings, owner, dataset, storage)
    index_chunks(settings, owner, dataset, doc["id"], plain=3, edited=1, manual=1)
    sql("UPDATE `document` SET `run` = '3', `progress` = 1 WHERE `id` = %s", (doc["id"],))
    before = (doc_state(doc["id"]), dataset_chunks(dataset.id), chunk_ids(settings, owner, dataset, doc["id"]))

    err = refused(lambda: start(settings, owner, dataset, [doc["id"]]))
    assert (err.kind, err.reason) == (Kind.CONFLICT, "confirm_required")
    assert err.data == {"documents": [{"id": doc["id"], "name": "a.txt", "chunk_count": 5, "edited_count": 1, "manual_count": 1}]}
    assert (doc_state(doc["id"]), dataset_chunks(dataset.id), chunk_ids(settings, owner, dataset, doc["id"])) == before
    assert tasks(doc["id"]) == [] and stream(settings) == [] and logs(doc["id"]) == []


def test_one_document_needing_confirmation_stops_the_whole_request(settings, space, storage):
    owner, dataset = space
    fresh = one_doc(settings, owner, dataset, storage, "fresh.txt")
    done = one_doc(settings, owner, dataset, storage, "done.txt")
    index_chunks(settings, owner, dataset, done["id"], plain=2)
    sql("UPDATE `document` SET `run` = '3', `progress` = 1 WHERE `id` = %s", (done["id"],))
    err = refused(lambda: start(settings, owner, dataset, [fresh["id"], done["id"]]))
    assert err.reason == "confirm_required" and [d["id"] for d in err.data["documents"]] == [done["id"]]
    assert doc_state(fresh["id"])[0] == "0" and tasks(fresh["id"]) == [] and stream(settings) == []


def test_a_confirmed_reparse_replaces_everything(settings, space, storage):
    owner, dataset = space
    doc = one_doc(settings, owner, dataset, storage)
    index_chunks(settings, owner, dataset, doc["id"], plain=3, edited=1, manual=1)
    sql("UPDATE `document` SET `run` = '3', `progress` = 1 WHERE `id` = %s", (doc["id"],))
    old_task = uuid.uuid4().hex
    sql("INSERT INTO `task` (`id`, `doc_id`, `from_page`, `to_page`, `progress`, `create_time`) VALUES (%s, %s, 0, 1000000, 1, 1)", (old_task, doc["id"]))
    with DB.connection_context():
        PipelineOperationLog.create(
            id=uuid.uuid4().hex, document_id=doc["id"], tenant_id=owner.tenant_id, kb_id=dataset.id, parser_id="naive", document_name="a.txt",
            document_suffix="txt", document_type="doc", source_from="local", operation_status="done", task_type="parse",
        )  # fmt: skip
    chunks_before = dataset_chunks(dataset.id)

    start(settings, owner, dataset, [doc["id"]], True)
    assert chunk_ids(settings, owner, dataset, doc["id"]) == []
    assert doc_state(doc["id"]) == ("1", 0.0, 0, 0)
    assert dataset_chunks(dataset.id) == chunks_before - 5
    assert old_task not in [r[0] for r in sql("SELECT `id` FROM `task` WHERE `doc_id` = %s", (doc["id"],))]
    assert len(tasks(doc["id"])) == 1 and len(stream(settings)) == 1
    assert logs(doc["id"]) == ["done", "running"]


def test_failed_or_cancelled_needs_confirmation_only_for_edited_or_manual_chunks(settings, space, storage):
    owner, dataset = space
    plain = one_doc(settings, owner, dataset, storage, "p.txt")
    edited = one_doc(settings, owner, dataset, storage, "e.txt")
    index_chunks(settings, owner, dataset, plain["id"], plain=2)
    index_chunks(settings, owner, dataset, edited["id"], plain=2, edited=1)
    sql("UPDATE `document` SET `run` = '4' WHERE `id` IN (%s, %s)", (plain["id"], edited["id"]))
    assert start(settings, owner, dataset, [plain["id"]])[0].task_count == 1
    assert chunk_ids(settings, owner, dataset, plain["id"]) == []
    err = refused(lambda: start(settings, owner, dataset, [edited["id"]]))
    assert err.reason == "confirm_required" and err.data["documents"][0]["edited_count"] == 1
    sql("UPDATE `document` SET `run` = '2' WHERE `id` = %s", (edited["id"],))
    assert refused(lambda: start(settings, owner, dataset, [edited["id"]])).reason == "confirm_required"


def test_a_never_started_document_with_a_manual_chunk_needs_confirmation(settings, space, storage):
    owner, dataset = space
    doc = one_doc(settings, owner, dataset, storage)
    index_chunks(settings, owner, dataset, doc["id"], manual=1)
    err = refused(lambda: start(settings, owner, dataset, [doc["id"]]))
    assert err.reason == "confirm_required" and err.data["documents"][0]["manual_count"] == 1


# ----------------------------------------------------------------------------- refusals


def unchanged(cfg, doc_id):
    return doc_state(doc_id), tasks(doc_id), logs(doc_id), stream(cfg)


def test_a_running_document_is_already_running(settings, space, storage):
    owner, dataset = space
    doc = one_doc(settings, owner, dataset, storage)
    sql("UPDATE `document` SET `run` = '1' WHERE `id` = %s", (doc["id"],))
    before = unchanged(settings, doc["id"])
    err = refused(lambda: start(settings, owner, dataset, [doc["id"]], True))
    assert (err.kind, err.reason) == (Kind.CONFLICT, "already_running") and unchanged(settings, doc["id"]) == before


def test_an_unknown_parser_is_parse_unavailable(settings, space, storage):
    owner, dataset = space
    doc = one_doc(settings, owner, dataset, storage)
    sql("UPDATE `document` SET `suffix` = 'unbuilt-fixture' WHERE `id` = %s", (doc["id"],))
    err = refused(lambda: start(settings, owner, dataset, [doc["id"]]))
    assert (err.kind, err.reason) == (Kind.INVALID, "parse_unavailable") and doc_state(doc["id"])[0] == "0"


def test_an_unimplemented_chunker_is_refused(settings, space, storage):
    owner, dataset = space
    doc = one_doc(settings, owner, dataset, storage)
    sql("UPDATE `document` SET `parser_id` = 'unbuilt-fixture' WHERE `id` = %s", (doc["id"],))
    err = refused(lambda: start(settings, owner, dataset, [doc["id"]]))
    assert (err.kind, err.reason) == (Kind.INVALID, "chunker_unavailable") and tasks(doc["id"]) == []


def test_a_removed_embedding_model_is_model_unavailable(settings, space, storage):
    owner, dataset = space
    doc = one_doc(settings, owner, dataset, storage)
    sql("UPDATE `knowledgebase` SET `embd_id` = 'ghost-model@VLLM' WHERE `id` = %s", (dataset.id,))
    err = refused(lambda: start(settings, owner, dataset, [doc["id"]]))
    assert (err.kind, err.reason) == (Kind.CONFLICT, "model_unavailable") and tasks(doc["id"]) == [] and stream(settings) == []


def test_permissions_follow_uploader_creator_owner_and_the_token_subject(settings, llm, registry, storage):
    owner, creator, writer, other = (registry.register(prefix=p) for p in ("ino", "inc", "inw", "ino2"))
    configure(llm, owner)
    for member in (creator, writer, other):
        join(owner, member)
    dataset = team_dataset_of(settings, owner, creator)
    mine = upload(settings, writer, dataset, [item("w.txt", text_bytes("w"))], storage=storage)[0]["id"]
    second = upload(settings, writer, dataset, [item("w2.txt", text_bytes("w2"))], storage=storage)[0]["id"]
    third = upload(settings, writer, dataset, [item("w3.txt", text_bytes("w3"))], storage=storage)[0]["id"]
    fourth = upload(settings, writer, dataset, [item("w4.txt", text_bytes("w4"))], storage=storage)[0]["id"]

    assert refused(lambda: start(settings, other, dataset, [mine])).kind is Kind.FORBIDDEN
    assert tasks(mine) == []
    token = Principal(owner.user_id, owner.tenant_id, "owner", AUTH_API, False)
    visible = ing.authorize_parse(token, dataset.id)
    assert refused(lambda: ing.start_parse(settings, visible, token, [mine], False)).kind is Kind.FORBIDDEN, "a token is not elevated"
    assert start(settings, writer, dataset, [mine])[0].task_count == 1
    assert start(settings, creator, dataset, [second])[0].task_count == 1
    assert start(settings, owner, dataset, [third])[0].task_count == 1
    assert refused(lambda: ing.cancel_parse(settings, ing.authorize_parse(principal_of(other), dataset.id), principal_of(other), [mine])).kind is Kind.FORBIDDEN
    assert tasks(fourth) == []


def test_foreign_ids_and_malformed_ids(settings, space, storage, llm, registry):
    owner, dataset = space
    stranger = registry.register(prefix="instr")
    configure(llm, stranger)
    foreign_dataset = base.make(settings, stranger)
    foreign = one_doc(settings, stranger, foreign_dataset, storage)
    mine = one_doc(settings, owner, dataset, storage)
    err = refused(lambda: start(settings, owner, dataset, [mine["id"], foreign["id"]]))
    assert (err.kind, err.reason) == (Kind.NOT_FOUND, "dataset_not_found") and tasks(mine["id"]) == []
    assert refused(lambda: start(settings, owner, dataset, [uuid.uuid4().hex])).kind is Kind.NOT_FOUND
    assert refused(lambda: ing.authorize_parse(principal_of(stranger), dataset.id)).kind is Kind.NOT_FOUND
    for bad in ([], ["nope"], [f"{i:032x}" for i in range(101)], "x"):
        assert refused(lambda ids=bad: start(settings, owner, dataset, ids)).reason == "ids_invalid"


# ----------------------------------------------------------------------------- queue outage


def test_a_closed_queue_is_503_and_changes_nothing(settings, space, storage):
    owner, dataset = space
    doc = one_doc(settings, owner, dataset, storage)
    index_chunks(settings, owner, dataset, doc["id"], plain=2)
    sql("UPDATE `document` SET `run` = '3' WHERE `id` = %s", (doc["id"],))
    down = dataclasses.replace(settings, redis=dataclasses.replace(settings.redis, port=1))
    before = (doc_state(doc["id"]), tasks(doc["id"]), logs(doc["id"]), chunk_ids(settings, owner, dataset, doc["id"]))
    err = refused(lambda: start(down, owner, dataset, [doc["id"]], True))
    assert (err.kind, err.reason) == (Kind.UNAVAILABLE, "queue_unavailable")
    assert (doc_state(doc["id"]), tasks(doc["id"]), logs(doc["id"]), chunk_ids(settings, owner, dataset, doc["id"])) == before


class _PublishFails:
    def ping(self) -> None:
        return None

    def enqueue(self, task_id: str, digest: str, priority: int = 0) -> str:
        raise QueueUnavailable("queue is not available")


def test_a_failed_publish_marks_the_documents_failed_and_answers_503(settings, space, storage):
    owner, dataset = space
    doc = one_doc(settings, owner, dataset, storage)
    err = refused(lambda: start(settings, owner, dataset, [doc["id"]], queue=_PublishFails()))
    assert (err.kind, err.reason) == (Kind.UNAVAILABLE, "queue_unavailable")
    run, progress, _, _ = doc_state(doc["id"])
    assert (run, progress) == ("4", -1.0) and logs(doc["id"]) == ["failed"]


# ----------------------------------------------------------------------------- cancel


def test_cancel_closes_the_log_and_keeps_chunks_and_counters(settings, space, storage):
    owner, dataset = space
    doc = one_doc(settings, owner, dataset, storage)
    start(settings, owner, dataset, [doc["id"]])
    ids = index_chunks(settings, owner, dataset, doc["id"], plain=2)
    visible = ing.authorize_parse(principal_of(owner), dataset.id)
    assert ing.cancel_parse(settings, visible, principal_of(owner), [doc["id"]]) == [doc["id"]]
    assert doc_state(doc["id"])[0] == "2" and logs(doc["id"]) == ["cancelled"]
    assert sorted(chunk_ids(settings, owner, dataset, doc["id"])) == sorted(ids)
    assert doc_state(doc["id"])[2:] == (2, 20)


def test_cancel_of_a_document_that_is_not_running_changes_nothing(settings, space, storage):
    owner, dataset = space
    doc = one_doc(settings, owner, dataset, storage)
    visible = ing.authorize_parse(principal_of(owner), dataset.id)
    before = unchanged(settings, doc["id"])
    assert ing.cancel_parse(settings, visible, principal_of(owner), [doc["id"]]) == []
    assert unchanged(settings, doc["id"]) == before
