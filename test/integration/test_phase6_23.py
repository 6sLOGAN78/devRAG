"""Dataset refresh against real MySQL, Elasticsearch and HTTP model transport."""
import json

import pytest

from api.db.database import DB
from api.db.models import DatasetJob, Document, Task
from api.db.services import dataset_job_service as jobs
from api.db.services import knowledgebase_service
from api.db.services import ingestion_read_service as reads
from api.db.services import task_service
from api.db.services import tenant_model_service as models
from api.db.services.service_errors import Kind, ServiceError
from common.model_ref import ModelRef
from rag.svr.control import TaskControl
from rag.svr.dataset_jobs import run_refresh
from rag.queue.queue_base import QueueUnavailable
from test.helpers.ingest import add_document, add_task, indexed, run_task
from test.helpers.uploads import sql
from rag.utils.storage_factory import get_storage
from test.integration import test_pipeline_failures as base
from test.integration.test_knowledgebase_service import principal_of

_bound_database = base._bound_database
registry = base.registry
fake = base.fake
world = base.world
pytestmark = pytest.mark.integration
MODEL = ModelRef("fake-job", "default", "OpenAI-API-Compatible").composite


class RecordingQueue:
    def __init__(self):
        self.messages = []

    def ping(self):
        return None

    def enqueue(self, task_id, digest, priority=0):
        self.messages.append((task_id, digest, priority))
        return str(len(self.messages))


def test_queue_outage_creates_no_partial_job(world):
    class UnavailableQueue(RecordingQueue):
        def ping(self):
            raise QueueUnavailable("offline")

    sql("UPDATE `knowledgebase` SET `parser_config`=%s WHERE `id`=%s", (json.dumps({"auto_keywords": 1}), world.dataset.id))
    with pytest.raises(ServiceError) as denied:
        jobs.start_job(world.settings, principal_of(world.owner), world.dataset.id, "enrich", queue=UnavailableQueue())
    assert denied.value.kind is Kind.UNAVAILABLE
    with DB.connection_context():
        assert not DatasetJob.select().where(DatasetJob.kb_id == world.dataset.id).exists()


def test_dataset_enrichment_refreshes_existing_source_without_reparse(world, fake, repo_root):
    source = (repo_root / "test/fixtures/phase6/controlled-enrichment-original.txt").read_bytes()
    doc_id = add_document(world, "job-source.txt", source)
    parse_task = add_task(doc_id)
    run_task(world, parse_task)
    sql("UPDATE `task` SET `progress`=1 WHERE `id`=%s", (parse_task,))
    sql("UPDATE `document` SET `run`='3', `chunk_num`=1 WHERE `id`=%s", (doc_id,))
    models.add_models(world.settings.llm, world.owner.tenant_id, "OpenAI-API-Compatible", "default", [models.NewModel("fake-job", "chat", None, 8192)])
    config = {"auto_tags": True, "allowed_tags": ["lighthouse", "calibration"], "tag_model_id": MODEL,
              "auto_metadata": True, "metadata_schema": [{"name": "tower_height_metres", "type": "number", "required": True}], "metadata_model_id": MODEL}
    sql("UPDATE `knowledgebase` SET `parser_config`=%s WHERE `id`=%s", (json.dumps(config), world.dataset.id))
    queue = RecordingQueue()
    principal = principal_of(world.owner)
    started = jobs.start_job(world.settings, principal, world.dataset.id, "enrich", queue=queue)
    assert started["run"] == "1" and started["total"] == 1 and len(queue.messages) == 1
    child = task_service.load_dataset_job_context(queue.messages[0][0])
    assert child is not None and child.doc_id == doc_id and child.job_id == started["id"]
    assert task_service.load_task_context(child.task_id) is None  # sentinel cannot join Document
    fake.chat_responses[:] = [json.dumps({"items": [{"index": 0, "tags": ["lighthouse"]}]}),
                             json.dumps({"metadata": {"tower_height_metres": 52}})]
    before = len(fake.chat_requests())
    result = run_refresh(child, TaskControl(), world.deps())
    task_service.mark_task_done(child.task_id, result.chunk_ids, 0.1)
    jobs.settle(child.job_id)
    assert len(fake.chat_requests()) == before + 2
    refreshed = indexed(world, doc_id=[doc_id])
    assert len(refreshed) == 1 and refreshed[0]["content_with_weight"] == source.decode().strip()
    assert refreshed[0]["tags_kwd"] == ["lighthouse"] and refreshed[0]["tags_source_kwd"] == "generated"
    with DB.connection_context():
        document = Document.get_by_id(doc_id)
        job = DatasetJob.get_by_id(child.job_id)
        task = Task.get_by_id(child.task_id)
    assert document.meta_fields["_generated"] == {"tower_height_metres": 52}
    assert job.status == "done" and task.progress == 1
    assert jobs.get_job(principal, world.dataset.id, child.job_id)["completed"] == 1
    task_view = reads.task_status(principal, child.task_id)
    assert task_view["job_id"] == child.job_id and task_view["doc_id"] == "" and task_view["finished"] is True


def test_cancelled_job_drops_child_before_model_or_source_access(world, fake, repo_root):
    source = (repo_root / "test/fixtures/phase6/controlled-enrichment-original.txt").read_bytes()
    doc_id = add_document(world, "cancel-source.txt", source)
    parse_task = add_task(doc_id)
    run_task(world, parse_task)
    sql("UPDATE `task` SET `progress`=1 WHERE `id`=%s", (parse_task,))
    sql("UPDATE `document` SET `run`='3', `chunk_num`=1 WHERE `id`=%s", (doc_id,))
    sql("UPDATE `knowledgebase` SET `parser_config`=%s WHERE `id`=%s", (json.dumps({"auto_keywords": 1}), world.dataset.id))
    principal = principal_of(world.owner)
    queue = RecordingQueue()
    started = jobs.start_job(world.settings, principal, world.dataset.id, "enrich", queue=queue)
    before = len(fake.chat_requests())
    assert jobs.cancel_job(principal, world.dataset.id, started["id"])["run"] == "2"
    assert task_service.load_dataset_job_context(queue.messages[0][0]) is None
    assert len(fake.chat_requests()) == before


def test_source_replacement_and_foreign_job_id_fail_closed(world, registry, fake, repo_root):
    doc_id = add_document(world, "stale-source.txt", (repo_root / "test/fixtures/phase6/controlled-enrichment-original.txt").read_bytes())
    parse_task = add_task(doc_id)
    run_task(world, parse_task)
    sql("UPDATE `task` SET `progress`=1 WHERE `id`=%s", (parse_task,))
    sql("UPDATE `document` SET `run`='3', `chunk_num`=1 WHERE `id`=%s", (doc_id,))
    sql("UPDATE `knowledgebase` SET `parser_config`=%s WHERE `id`=%s", (json.dumps({"auto_keywords": 1}), world.dataset.id))
    queue = RecordingQueue()
    principal = principal_of(world.owner)
    started = jobs.start_job(world.settings, principal, world.dataset.id, "enrich", queue=queue)
    outsider = registry.register(prefix="job-outsider")
    with pytest.raises(ServiceError) as denied:
        jobs.get_job(principal_of(outsider), world.dataset.id, started["id"])
    assert denied.value.kind is Kind.NOT_FOUND
    with pytest.raises(ServiceError) as duplicate:
        jobs.start_job(world.settings, principal, world.dataset.id, "enrich", queue=queue)
    assert duplicate.value.reason == "already_running" and len(queue.messages) == 1
    sql("DELETE FROM `task` WHERE `id`=%s", (parse_task,))
    assert task_service.load_dataset_job_context(queue.messages[0][0]) is None
    jobs.fail_stale_child(queue.messages[0][0])
    assert jobs.get_job(principal, world.dataset.id, started["id"])["run"] == "4"
    assert len(fake.chat_requests()) == 0


def test_dataset_deletion_removes_job_sentinel_children(world, repo_root):
    doc_id = add_document(world, "delete-source.txt", (repo_root / "test/fixtures/phase6/controlled-enrichment-original.txt").read_bytes())
    parse_task = add_task(doc_id)
    run_task(world, parse_task)
    sql("UPDATE `task` SET `progress`=1 WHERE `id`=%s", (parse_task,))
    sql("UPDATE `document` SET `run`='3', `chunk_num`=1 WHERE `id`=%s", (doc_id,))
    sql("UPDATE `knowledgebase` SET `parser_config`=%s WHERE `id`=%s", (json.dumps({"auto_keywords": 1}), world.dataset.id))
    started = jobs.start_job(world.settings, principal_of(world.owner), world.dataset.id, "enrich", queue=RecordingQueue())
    assert knowledgebase_service.delete_datasets(world.settings, principal_of(world.owner), [world.dataset.id],
                                                 storage=get_storage(world.settings), doc_store=world.store()) == [world.dataset.id]
    with DB.connection_context():
        assert DatasetJob.get_or_none(DatasetJob.id == started["id"]) is None
        assert not Task.select().where(Task.doc_id == started["id"]).exists()
