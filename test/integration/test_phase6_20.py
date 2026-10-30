"""Actual MySQL and Elasticsearch document metadata contract."""
import json

import pytest

from api.db.database import DB
from test.integration import test_pipeline_failures as base
from test.helpers.ingest import add_document, add_task, indexed, run_task
from test.helpers.uploads import sql

_bound_database = base._bound_database
registry = base.registry
fake = base.fake
world = base.world
pytestmark = pytest.mark.integration


def _prepared(world, repo_root):
    from test.integration.test_knowledgebase_service import principal_of

    path = repo_root / "test/fixtures/phase6/tags-original.txt"
    first = add_document(world, path.name, path.read_bytes())
    second = add_document(world, "second.txt", path.read_bytes())
    for doc in (first, second):
        run_task(world, add_task(doc))
        sql("UPDATE `document` SET `run`='3' WHERE `id`=%s", (doc,))
    return (first, second), principal_of(world.owner)


def test_batch_metadata_persists_and_updates_index_without_rewriting_source(world, repo_root):
    from api.db.models import Document
    from api.db.services import document_metadata_service as metadata

    docs, principal = _prepared(world, repo_root)
    before = indexed(world, doc_id=[docs[0]])[0]
    selected = {key: before[key] for key in ("content_with_weight", "position_int", "q_8_vec", "source_lines_int") if key in before}
    result = metadata.batch_edit_metadata(world.settings, principal, world.dataset.id, list(docs), {"subject": "lighthouse", "height_metres": 52}, "merge", doc_store=world.store())
    assert result == {"document_ids": list(docs), "count": 2}
    with DB.connection_context():
        stored = {row.id: row.meta_fields for row in Document.select().where(Document.id.in_(docs))}
    assert all(value == {"subject": "lighthouse", "height_metres": 52} for value in stored.values())
    assert json.loads(indexed(world, doc_id=[docs[0]])[0][metadata.INDEX_FIELD]) == stored[docs[0]]
    assert {key: indexed(world, doc_id=[docs[0]])[0][key] for key in selected} == selected
    assert metadata.get_flattened_metadata(principal, [world.dataset.id])["fields"] == [
        {"name": "height_metres", "type": "number", "total": 1, "values": [52]},
        {"name": "subject", "type": "string", "total": 1, "values": ["lighthouse"]},
    ]
    assert metadata.get_metadata_config(principal, world.dataset.id) == {"enabled": False, "schema": [], "model_id": ""}
    # The worker reads the persisted document fields again after a later parse.
    run_task(world, add_task(docs[0]))
    reparsed = indexed(world, doc_id=[docs[0]])[0]
    assert json.loads(reparsed[metadata.INDEX_FIELD]) == stored[docs[0]]
    assert reparsed["content_with_weight"] == before["content_with_weight"]


def test_metadata_batch_rejects_foreign_id_and_active_parse_atomically(world, repo_root):
    from api.db.models import Document
    from api.db.services import document_metadata_service as metadata
    from api.db.services.service_errors import ServiceError

    docs, principal = _prepared(world, repo_root)
    class NoRead:
        def search(self, *args, **kwargs):
            pytest.fail("index queried before all selected documents were authorized")
    with pytest.raises(ServiceError) as missing:
        metadata.batch_edit_metadata(world.settings, principal, world.dataset.id, [docs[0], "f" * 32], {"reviewed": True}, "merge", doc_store=NoRead())
    assert missing.value.reason == "dataset_not_found"
    sql("UPDATE `document` SET `run`='1' WHERE `id`=%s", (docs[1],))
    with pytest.raises(ServiceError) as err:
        metadata.batch_edit_metadata(world.settings, principal, world.dataset.id, list(docs), {"reviewed": True}, "merge", doc_store=NoRead())
    assert err.value.reason == "parse_running"
    with DB.connection_context():
        assert all(row.meta_fields == {} for row in Document.select().where(Document.id.in_(docs)))
