"""Derived deletion and artifact ownership on real MySQL, MinIO and Elasticsearch."""
import json

import pytest

from api.db.database import DB
from api.db.models import DatasetAlteration, DatasetJob, Document, DocumentAsset
from api.db.services import dataset_artifact_service as artifacts
from api.db.services import dataset_job_service as jobs
from api.db.services import task_service
from api.db.services import tenant_model_service as models
from api.db.services.service_errors import Kind, ServiceError
from common.doc_store.doc_store_base import DocStoreError
from common.model_ref import ModelRef
from rag.svr.control import TaskCancelled, TaskControl
from rag.svr.dataset_jobs import run_raptor
from rag.utils.storage_factory import get_storage
from test.helpers.ingest import add_document, add_task, indexed, run_task
from test.helpers.uploads import sql
from test.integration import test_pipeline_failures as base
from test.integration.test_knowledgebase_service import principal_of

_bound_database = base._bound_database
registry = base.registry
fake = base.fake
world = base.world
pytestmark = pytest.mark.integration


class Queue:
    def __init__(self): self.task = None
    def ping(self): pass
    def enqueue(self, task_id, digest, priority=0): self.task = task_id; return "1"


def prepare(world, repo_root):
    source = (repo_root / "test/fixtures/phase6/raptor-original.txt").read_bytes()
    doc_id = add_document(world, "artifact-source.txt", source, parser_config={"chunk_token_num": 32, "delimiter": "\n", "overlapped_percent": 0})
    parse_task = add_task(doc_id)
    run_task(world, parse_task)
    assert len(indexed(world, doc_id=[doc_id])) == 6
    sql("UPDATE `task` SET `progress`=1 WHERE `id`=%s", (parse_task,))
    sql("UPDATE `document` SET `run`='3', `chunk_num`=6 WHERE `id`=%s", (doc_id,))
    models.add_models(world.settings.llm, world.owner.tenant_id, "OpenAI-API-Compatible", "default", [models.NewModel("fake-artifact", "chat", None, 8192)])
    models.set_defaults(world.owner.tenant_id, chat=ModelRef("fake-artifact", "default", "OpenAI-API-Compatible"))
    sql("UPDATE `knowledgebase` SET `parser_config`=%s WHERE `id`=%s", (json.dumps({"raptor": True}), world.dataset.id))
    queue = Queue()
    principal = principal_of(world.owner)
    started = jobs.start_job(world.settings, principal, world.dataset.id, "raptor", queue=queue)
    child = task_service.load_dataset_job_context(queue.task)
    assert child is not None
    return doc_id, principal, started, child


def test_download_then_delete_only_derived_rows_and_audit_the_result(world, fake, registry, repo_root):
    doc_id, principal, started, child = prepare(world, repo_root)
    fake.chat_responses[:] = [f"Pair {i}: lighthouse height 52 metres and calibration offset 73 units." for i in range(3)] + ["All six sources agree: height 52 metres, offset 73 units."]
    result = run_raptor(child, TaskControl(), world.deps())
    task_service.mark_task_done(child.task_id, result.chunk_ids, 0.1)
    jobs.settle(child.job_id)
    finished = jobs.get_job(principal, world.dataset.id, started["id"])
    filename = finished["artifact_filename"]
    assert filename and filename.endswith(".json")
    content = json.loads(artifacts.read_artifact(world.settings, principal, filename,
                                                  doc_store=world.store(), storage=get_storage(world.settings)))
    assert content["generation"] == started["id"] and len(content["summaries"]) == 4
    assert "52" in content["summaries"][-1]["text"]
    assert len(content["summaries"][-1]["source_leaf_ids"]) == 6
    outsider = registry.register(prefix="artifact-outsider")
    with pytest.raises(ServiceError) as denied:
        artifacts.read_artifact(world.settings, principal_of(outsider), filename, doc_store=world.store())
    assert denied.value.kind is Kind.NOT_FOUND
    for malformed in ("../" + filename, filename.replace(".json", ".txt"), "%2F" + filename):
        with pytest.raises(ServiceError) as rejected:
            artifacts.read_artifact(world.settings, principal, malformed, doc_store=world.store())
        assert rejected.value.kind is Kind.NOT_FOUND
    removed = artifacts.delete_derived_index(world.settings, principal, world.dataset.id, "raptor",
                                              doc_store=world.store(), storage=get_storage(world.settings))
    assert removed == {"type": "raptor", "deleted_count": 4, "artifact_count": 1}
    remaining = indexed(world, doc_id=[doc_id])
    assert len(remaining) == 6 and all(row.get("origin_kwd") != "raptor" for row in remaining)
    with DB.connection_context():
        assert Document.get_or_none(Document.id == doc_id) is not None
        assert DocumentAsset.get_or_none(DocumentAsset.id == filename[:-5]) is None
    with pytest.raises(ServiceError) as gone:
        artifacts.read_artifact(world.settings, principal, filename, doc_store=world.store())
    assert gone.value.kind is Kind.NOT_FOUND
    history = artifacts.list_alterations(principal, world.dataset.id, page=1, size=1)
    assert history["total"] == 1 and history["items"] == [{
        "actor": world.owner.user_id, "type": "raptor", "generation": started["id"],
        "outcome": "done", "time": history["items"][0]["time"], "deleted_count": 4}]
    again = artifacts.delete_derived_index(world.settings, principal, world.dataset.id, "raptor",
                                            doc_store=world.store(), storage=get_storage(world.settings))
    assert again["deleted_count"] == 0 and again["artifact_count"] == 0
    assert artifacts.list_alterations(principal, world.dataset.id, size=1)["total"] == 2


def test_active_generation_is_cancelled_before_delete_and_bad_type_cannot_touch_sources(world, fake, repo_root):
    doc_id, principal, started, child = prepare(world, repo_root)
    with pytest.raises(ServiceError) as bad:
        artifacts.delete_derived_index(world.settings, principal, world.dataset.id, "all", doc_store=world.store())
    assert bad.value.kind is Kind.NOT_FOUND
    assert jobs.get_job(principal, world.dataset.id, started["id"])["run"] == "1"
    removed = artifacts.delete_derived_index(world.settings, principal, world.dataset.id, "raptor",
                                              doc_store=world.store(), storage=get_storage(world.settings))
    assert removed["deleted_count"] == 0
    with pytest.raises(TaskCancelled):
        run_raptor(child, TaskControl(), world.deps())
    assert jobs.get_job(principal, world.dataset.id, started["id"])["run"] == "2"
    assert len(indexed(world, doc_id=[doc_id])) == 6


def test_index_failure_is_audited_and_never_reports_success(world, fake, repo_root):
    doc_id, principal, started, _child = prepare(world, repo_root)
    class FailingDelete:
        def delete(self, *_args):
            raise DocStoreError("delete failed")
    with pytest.raises(ServiceError) as failed:
        artifacts.delete_derived_index(world.settings, principal, world.dataset.id, "raptor", doc_store=FailingDelete())
    assert failed.value.kind is Kind.UNAVAILABLE
    assert jobs.get_job(principal, world.dataset.id, started["id"])["run"] == "2"
    assert len(indexed(world, doc_id=[doc_id])) == 6
    history = artifacts.list_alterations(principal, world.dataset.id)
    assert history["total"] == 1 and history["items"][0]["outcome"] == "failed"
