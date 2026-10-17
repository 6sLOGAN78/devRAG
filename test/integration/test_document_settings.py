"""Changing one document's chunking settings against the real MySQL and Elasticsearch (plan 04-16; DOC-12, CHUNK-02, D-02, D-15, D-27)."""

from __future__ import annotations

import pytest

from api.db.services import document_service as docsvc
from api.db.services import knowledgebase_service as kbsvc
from api.db.services.auth_service import AUTH_API, Principal
from api.db.services.service_errors import Kind
from test.helpers.uploads import sql, text_bytes
from test.integration import test_ingestion_service as ingest
from test.integration.test_document_service import chunk_ids, team_dataset_of
from test.integration.test_knowledgebase_service import configure, join, principal_of

pytestmark = pytest.mark.integration

_bound_database = ingest._bound_database
settings = ingest.settings
llm = ingest.llm
registry = ingest.registry
storage = ingest.storage
space = ingest.space
item = ingest.item
upload = ingest.upload
refused = ingest.refused
one_doc = ingest.one_doc
index_chunks = ingest.index_chunks


def change(cfg, who, dataset, doc_id, parser_id=None, parser_config=None, principal=None):
    principal = principal or principal_of(who)
    visible = docsvc.authorize_removal(principal, dataset.id)
    return docsvc.update_document_settings(cfg, visible, principal, doc_id, parser_id, parser_config)


def row_of(doc_id: str) -> tuple:
    return sql("SELECT `parser_id`, `parser_config`, `run`, `progress`, `chunk_num`, `update_time` FROM `document` WHERE `id` = %s", (doc_id,))[0]


def stored_config(doc_id: str) -> dict:
    import json

    raw = sql("SELECT `parser_config` FROM `document` WHERE `id` = %s", (doc_id,))[0][0]
    return raw if isinstance(raw, dict) else json.loads(raw)


def test_the_uploader_changes_the_three_chunking_values_and_nothing_else(settings, space, storage):
    owner, dataset = space
    doc = one_doc(settings, owner, dataset, storage)
    before = row_of(doc["id"])
    change(settings, owner, dataset, doc["id"], None, {"chunk_token_num": 256, "delimiter": "##", "overlapped_percent": 10})
    after = row_of(doc["id"])
    config = stored_config(doc["id"])
    assert (config["chunk_token_num"], config["delimiter"], config["overlapped_percent"]) == (256, "##", 10)
    assert (after[0], after[2], after[3], after[4]) == (before[0], before[2], before[3], before[4])
    assert after[5] >= before[5]


def test_a_change_keeps_chunks_run_and_the_index_untouched(settings, space, storage):
    owner, dataset = space
    doc = one_doc(settings, owner, dataset, storage)
    ids = index_chunks(settings, owner, dataset, doc["id"], plain=3)
    sql("UPDATE `document` SET `run` = '3', `progress` = 1 WHERE `id` = %s", (doc["id"],))
    before = row_of(doc["id"])
    change(settings, owner, dataset, doc["id"], None, {"chunk_token_num": 128})
    after = row_of(doc["id"])
    assert (after[2], after[3], after[4]) == (before[2], before[3], before[4]) == ("3", 1.0, 3)
    assert chunk_ids(settings, owner, dataset, doc["id"]) == sorted(ids)
    assert len(chunk_ids(settings, owner, dataset, doc["id"])) == 3


def test_parser_id_can_be_set_to_a_built_method(settings, space, storage):
    owner, dataset = space
    doc = one_doc(settings, owner, dataset, storage)
    change(settings, owner, dataset, doc["id"], "naive", None)
    assert row_of(doc["id"])[0] == "naive"


def test_an_unbuilt_method_is_refused_and_nothing_changes(settings, space, storage):
    owner, dataset = space
    doc = one_doc(settings, owner, dataset, storage)
    before = row_of(doc["id"])
    err = refused(lambda: change(settings, owner, dataset, doc["id"], "qa", {"chunk_token_num": 64}))
    assert (err.kind, err.reason) == (Kind.INVALID, "chunker_unavailable")
    assert row_of(doc["id"]) == before


def test_an_unknown_method_is_parser_invalid(settings, space, storage):
    owner, dataset = space
    doc = one_doc(settings, owner, dataset, storage)
    assert refused(lambda: change(settings, owner, dataset, doc["id"], "nope", None)).reason == "parser_invalid"


def test_a_bad_value_is_parser_config_invalid_with_the_field(settings, space, storage):
    owner, dataset = space
    doc = one_doc(settings, owner, dataset, storage)
    before = row_of(doc["id"])
    err = refused(lambda: change(settings, owner, dataset, doc["id"], None, {"chunk_token_num": 0}))
    assert (err.kind, err.reason, err.data) == (Kind.INVALID, "parser_config_invalid", {"field": "chunk_token_num"})
    assert row_of(doc["id"]) == before


def test_a_running_document_is_refused_with_parse_running(settings, space, storage):
    owner, dataset = space
    doc = one_doc(settings, owner, dataset, storage)
    sql("UPDATE `document` SET `run` = '1' WHERE `id` = %s", (doc["id"],))
    before = row_of(doc["id"])
    err = refused(lambda: change(settings, owner, dataset, doc["id"], None, {"chunk_token_num": 64}))
    assert (err.kind, err.reason) == (Kind.CONFLICT, "parse_running")
    assert row_of(doc["id"]) == before


def test_unknown_and_foreign_documents_are_the_one_not_found(settings, space, storage):
    owner, dataset = space
    err = refused(lambda: change(settings, owner, dataset, "0" * 32, None, {"chunk_token_num": 64}))
    assert err.kind is Kind.NOT_FOUND
    err = refused(lambda: change(settings, owner, dataset, "not-an-id", None, {"chunk_token_num": 64}))
    assert err.kind is Kind.NOT_FOUND


def test_who_may_change_follows_uploader_creator_owner_and_the_token_subject(settings, llm, registry, storage):
    owner, creator, writer, other = (registry.register(prefix=p) for p in ("dso", "dsc", "dsw", "dso2"))
    configure(llm, owner)
    for member in (creator, writer, other):
        join(owner, member)
    dataset = team_dataset_of(settings, owner, creator)
    mine = upload(settings, writer, dataset, [item("w.txt", text_bytes("w"))], storage=storage)[0]["id"]
    values = {"chunk_token_num": 100}

    assert refused(lambda: change(settings, other, dataset, mine, None, values)).kind is Kind.FORBIDDEN
    token = Principal(owner.user_id, owner.tenant_id, "owner", AUTH_API, False)
    assert refused(lambda: change(settings, owner, dataset, mine, None, values, principal=token)).kind is Kind.FORBIDDEN, "a token is not elevated"
    for who in (writer, creator, owner):
        values = {"chunk_token_num": values["chunk_token_num"] + 1}
        change(settings, who, dataset, mine, None, values)
        assert stored_config(mine)["chunk_token_num"] == values["chunk_token_num"]


def test_dataset_update_refuses_an_unbuilt_method(settings, space):
    owner, dataset = space
    visible = kbsvc.load_visible_dataset(principal_of(owner), dataset.id)
    err = refused(lambda: kbsvc.update_dataset(settings, visible, owner.user_id, {"parser_id": "qa"}))
    assert (err.kind, err.reason) == (Kind.INVALID, "chunker_unavailable")
    assert kbsvc.load_visible_dataset(principal_of(owner), dataset.id).dataset.parser_id == dataset.parser_id
