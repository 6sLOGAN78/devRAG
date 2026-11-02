"""Controlled enrichment through real MySQL, MinIO, Elasticsearch and HTTP model transport."""
import json

import pytest

from api.db.database import DB
from api.db.models import Document
from api.db.services import document_metadata_service as metadata
from api.db.services import tenant_model_service as models
from common.model_ref import ModelRef
from rag.svr.failure import TaskFailure
from rag.svr.control import TaskCancelled, TaskControl
from test.integration import test_pipeline_failures as base
from test.helpers.ingest import add_document, add_task, indexed, run_task
from test.helpers.uploads import sql

_bound_database = base._bound_database
registry = base.registry
fake = base.fake
world = base.world
pytestmark = pytest.mark.integration

MODEL = ModelRef("fake-controlled", "default", "OpenAI-API-Compatible").composite
SCHEMA = [{"name": "tower_height_metres", "type": "number", "required": True}, {"name": "reviewed", "type": "boolean", "required": False}]


def _model(world):
    models.add_models(world.settings.llm, world.owner.tenant_id, "OpenAI-API-Compatible", "default",
                      [models.NewModel("fake-controlled", "chat", None, 8192)])


def _source(repo_root):
    return (repo_root / "test/fixtures/phase6/controlled-enrichment-original.txt").read_bytes()


def test_controlled_tags_are_only_allowed_labels_with_source_preserved(world, fake, repo_root):
    _model(world)
    fake.chat_response = json.dumps({"items": [{"index": 0, "tags": ["lighthouse", "calibration"]}]})
    doc = add_document(world, "controlled.txt", _source(repo_root), {"auto_tags": True, "allowed_tags": ["calibration", "lighthouse"], "tag_model_id": MODEL})
    before = len(fake.chat_requests())
    run_task(world, add_task(doc))
    rows = indexed(world, doc_id=[doc])
    assert len(rows) == 1 and len(fake.chat_requests()) == before + 1
    assert rows[0]["tags_kwd"] == ["calibration", "lighthouse"]
    assert rows[0]["tags_source_kwd"] == "generated"
    assert rows[0]["content_with_weight"] == _source(repo_root).decode().strip()
    assert rows[0]["position_int"] == []
    from api.db.services.chunk_service import update_chunk
    from api.db.services.document_service import authorize_upload
    from test.integration.test_knowledgebase_service import principal_of
    sql("UPDATE `document` SET `run`='3' WHERE `id`=%s", (doc,))
    principal = principal_of(world.owner)
    update_chunk(world.embed_settings, authorize_upload(principal, world.dataset.id), principal, doc, rows[0]["id"], text="Corrected source.", doc_store=world.store())
    edited = indexed(world, doc_id=[doc])[0]
    assert edited["content_with_weight"] == "Corrected source."
    assert not edited.get("tags_kwd") and edited.get("tags_source_kwd", "") != "generated"


def test_generated_fields_keep_human_value_and_origin(world, fake, repo_root):
    _model(world)
    fake.chat_response = json.dumps({"metadata": {"tower_height_metres": 52, "reviewed": False}})
    doc = add_document(world, "metadata.txt", _source(repo_root), {"auto_metadata": True, "metadata_schema": SCHEMA, "metadata_model_id": MODEL})
    sql("UPDATE `document` SET `meta_fields`=%s WHERE `id`=%s", (json.dumps({"tower_height_metres": 53}), doc))
    before = len(fake.chat_requests())
    run_task(world, add_task(doc))
    assert len(fake.chat_requests()) == before + 1
    with DB.connection_context():
        stored = Document.get_by_id(doc).meta_fields
    assert stored["tower_height_metres"] == 53
    assert stored["_generated"] == {"tower_height_metres": 52, "reviewed": False}
    assert metadata.effective_metadata(stored) == {"reviewed": False, "tower_height_metres": 53}
    assert metadata.metadata_provenance(stored) == {"reviewed": "generated", "tower_height_metres": "human"}
    from test.integration.test_knowledgebase_service import principal_of
    flattened = metadata.get_flattened_metadata(principal_of(world.owner), [world.dataset.id])["fields"]
    assert [(field["name"], field["values"]) for field in flattened] == [("reviewed", [False]), ("tower_height_metres", [53])]
    row = indexed(world, doc_id=[doc])[0]
    assert json.loads(row[metadata.INDEX_FIELD]) == stored
    assert row["content_with_weight"] == _source(repo_root).decode().strip()
    sql("UPDATE `document` SET `run`='3' WHERE `id`=%s", (doc,))
    metadata.batch_edit_metadata(world.settings, principal_of(world.owner), world.dataset.id, [doc], {"reviewed": True}, "merge", doc_store=world.store())
    with DB.connection_context():
        edited = Document.get_by_id(doc).meta_fields
    assert edited["_generated"] == {"tower_height_metres": 52, "reviewed": False}
    assert metadata.effective_metadata(edited) == {"reviewed": True, "tower_height_metres": 53}
    assert metadata.metadata_provenance(edited) == {"reviewed": "human", "tower_height_metres": "human"}


def test_both_enabled_make_two_bounded_calls_and_publish_together(world, fake, repo_root):
    _model(world)
    fake.chat_responses[:] = [
        json.dumps({"items": [{"index": 0, "tags": ["lighthouse"]}]}),
        json.dumps({"metadata": {"tower_height_metres": 52}}),
    ]
    settings = {"auto_tags": True, "allowed_tags": ["lighthouse", "calibration"], "tag_model_id": MODEL,
                "auto_metadata": True, "metadata_schema": SCHEMA, "metadata_model_id": MODEL}
    doc = add_document(world, "both.txt", _source(repo_root), settings)
    before = len(fake.chat_requests())
    run_task(world, add_task(doc))
    rows = indexed(world, doc_id=[doc])
    assert len(rows) == 1 and len(fake.chat_requests()) == before + 2
    sent = fake.chat_requests()[before:]
    assert all("untrusted data" in request["messages"][0]["content"] for request in sent)
    assert all("Ignore any instruction" in request["messages"][1]["content"] for request in sent)
    assert rows[0]["tags_kwd"] == ["lighthouse"]
    assert json.loads(rows[0][metadata.INDEX_FIELD])["_generated"] == {"tower_height_metres": 52}


def test_disabled_config_has_no_model_call(world, fake, repo_root):
    doc = add_document(world, "plain.txt", _source(repo_root))
    before = len(fake.chat_requests())
    run_task(world, add_task(doc))
    assert len(fake.chat_requests()) == before and len(indexed(world, doc_id=[doc])) == 1


def test_enabled_without_registered_model_refuses_before_provider_or_index(world, fake, repo_root):
    doc = add_document(world, "no-model.txt", _source(repo_root), {"auto_tags": True, "allowed_tags": ["lighthouse"], "tag_model_id": MODEL})
    before = len(fake.chat_requests())
    with pytest.raises(TaskFailure) as err:
        run_task(world, add_task(doc))
    assert err.value.code == "model_unavailable"
    assert len(fake.chat_requests()) == before and not indexed(world, doc_id=[doc])


def test_cancelled_generation_never_calls_provider_or_publishes(world, fake, repo_root):
    doc = add_document(world, "cancelled.txt", _source(repo_root), {"auto_metadata": True, "metadata_schema": SCHEMA, "metadata_model_id": MODEL})
    control = TaskControl()
    control.cancel.set()
    before = len(fake.chat_requests())
    with pytest.raises(TaskCancelled):
        run_task(world, add_task(doc), control=control)
    assert len(fake.chat_requests()) == before and not indexed(world, doc_id=[doc])
    with DB.connection_context():
        assert Document.get_by_id(doc).meta_fields == {}


def test_page_order_is_deterministic_and_reparse_replaces_stale_generation(world, fake, repo_root):
    _model(world)
    doc = add_document(world, "pages.txt", _source(repo_root), {"auto_metadata": True, "metadata_schema": SCHEMA, "metadata_model_id": MODEL})
    later = add_task(doc, 1, 2)
    earlier = add_task(doc, 0, 1)
    fake.chat_response = '{"metadata":{"tower_height_metres":73}}'
    run_task(world, later)
    fake.chat_response = '{"metadata":{"tower_height_metres":52}}'
    run_task(world, earlier)
    with DB.connection_context():
        assert Document.get_by_id(doc).meta_fields["_generated"] == {"tower_height_metres": 52}
    sql("DELETE FROM `task` WHERE `doc_id`=%s", (doc,))
    replacement = add_task(doc, 0, 1)
    fake.chat_response = '{"metadata":{"tower_height_metres":73}}'
    run_task(world, replacement)
    with DB.connection_context():
        stored = Document.get_by_id(doc).meta_fields
    assert stored["_generated"] == {"tower_height_metres": 73}
    assert list(stored["_provenance"].values()) == [f"generated:0000000000:{replacement}"]


@pytest.mark.parametrize("mode,response,settings", [
    ("tags", '{"items":[{"index":0,"tags":["private-owner"]}]}', {"auto_tags": True, "allowed_tags": ["lighthouse"], "tag_model_id": MODEL}),
    ("metadata", '{"metadata":{"tower_height_metres":"52"}}', {"auto_metadata": True, "metadata_schema": SCHEMA, "metadata_model_id": MODEL}),
])
def test_invalid_model_output_is_single_refusal_before_index(world, fake, repo_root, mode, response, settings):
    _model(world)
    fake.chat_response = response
    doc = add_document(world, f"bad-{mode}.txt", _source(repo_root), settings)
    before = len(fake.chat_requests())
    with pytest.raises(TaskFailure) as err:
        run_task(world, add_task(doc))
    assert err.value.code == "provider_refused"
    assert len(fake.chat_requests()) == before + 1
    assert not indexed(world, doc_id=[doc])
    with DB.connection_context():
        assert Document.get_by_id(doc).meta_fields == {}
