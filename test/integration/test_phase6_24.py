"""RAPTOR summaries on real MySQL/Elasticsearch with the local model wire."""
import json

import pytest

from api.db.services import dataset_job_service as jobs
from api.db.services import retrieval_service
from api.db.services.raptor_visibility import visible_summaries
from api.db.services import task_service
from api.db.services import tenant_model_service as models
from common.model_ref import ModelRef
from common.settings import DeepDocSettings
from rag.parsers.deepdoc_client import DeepDocClient
from rag.svr.control import TaskControl
from rag.svr.dataset_jobs import run_raptor
from test.helpers.ingest import add_document, add_task, indexed, run_task
from test.helpers.uploads import sql
from test.integration import test_pipeline_failures as base
from test.integration.test_knowledgebase_service import principal_of
from test.integration.test_retrieval_service import scope_of
from test.conftest import stack_env

_bound_database = base._bound_database
registry = base.registry
fake = base.fake
world = base.world
pytestmark = pytest.mark.integration


def test_native_seeded_umap_gmm_covers_every_leaf_twice_identically():
    token = stack_env().get("DEEPDOC_API_TOKEN")
    assert token, "real approved DeepDoc service is required"
    client = DeepDocClient(DeepDocSettings(url="http://127.0.0.1:9390", api_token=token, timeout_seconds=65))
    vectors = [[float(i + 1), float(9 - i)] for i in range(9)]
    first = client.raptor_clusters(vectors, 42)
    assert first == client.raptor_clusters(vectors, 42)
    assert sorted(i for group in first for i in group) == list(range(9))
    assert all(2 <= len(group) <= 8 for group in first)


def test_raptor_job_spans_documents_and_hides_when_any_source_changes(world, fake, repo_root):
    source = (repo_root / "test/fixtures/phase6/controlled-enrichment-original.txt").read_bytes()
    doc_id = add_document(world, "raptor-source.txt", source)
    parse_task = add_task(doc_id)
    run_task(world, parse_task)
    sql("UPDATE `task` SET `progress`=1 WHERE `id`=%s", (parse_task,))
    sql("UPDATE `document` SET `run`='3', `chunk_num`=1 WHERE `id`=%s", (doc_id,))
    other_id = add_document(world, "raptor-other.txt", b"A second original passage confirms the fictional 52 metre lighthouse.")
    other_task = add_task(other_id)
    run_task(world, other_task)
    sql("UPDATE `task` SET `progress`=1 WHERE `id`=%s", (other_task,))
    sql("UPDATE `document` SET `run`='3', `chunk_num`=1 WHERE `id`=%s", (other_id,))
    models.add_models(world.settings.llm, world.owner.tenant_id, "OpenAI-API-Compatible", "default", [models.NewModel("fake-raptor", "chat", None, 8192)])
    models.set_defaults(world.owner.tenant_id, chat=ModelRef("fake-raptor", "default", "OpenAI-API-Compatible"))
    sql("UPDATE `knowledgebase` SET `parser_config`=%s WHERE `id`=%s", (json.dumps({"raptor": True}), world.dataset.id))
    class Queue:
        def __init__(self): self.task = None
        def ping(self): pass
        def enqueue(self, task_id, digest, priority=0): self.task = task_id; return "1"
    queue = Queue()
    started = jobs.start_job(world.settings, principal_of(world.owner), world.dataset.id, "raptor", queue=queue)
    child = task_service.load_dataset_job_context(queue.task)
    assert started["type"] == "raptor" and started["run"] == "1" and started["total"] == 1
    assert child is not None and set(child.source_doc_ids) == {doc_id, other_id}
    fake.chat_responses[:] = ["Both original passages agree that the fictional lighthouse is 52 metres high."]
    result = run_raptor(child, TaskControl(), world.deps())
    assert len(result.chunk_ids) == 1
    summary = next(row for row in indexed(world) if row.get("origin_kwd") == "raptor")
    assert visible_summaries([summary], world.store(), world.owner.tenant_id, [world.dataset.id]) == {}, "an unfinished generation is invisible"
    task_service.mark_task_done(child.task_id, result.chunk_ids, 0.1)
    jobs.settle(child.job_id)
    visible = visible_summaries([summary], world.store(), world.owner.tenant_id, [world.dataset.id])
    assert {leaf["doc_id"] for leaf in visible[summary["id"]]} == {doc_id, other_id}
    sql("UPDATE `document` SET `status`='0' WHERE `id`=%s", (other_id,))
    assert visible_summaries([summary], world.store(), world.owner.tenant_id, [world.dataset.id]) == {}


def test_two_level_summaries_retrieve_only_with_current_source(world, fake, repo_root):
    source = (repo_root / "test/fixtures/phase6/raptor-original.txt").read_bytes()
    doc_id = add_document(world, "raptor-six.txt", source, parser_config={"chunk_token_num": 32, "delimiter": "\n", "overlapped_percent": 0})
    parse_task = add_task(doc_id)
    run_task(world, parse_task)
    leaves = indexed(world, doc_id=[doc_id])
    assert len(leaves) == 6
    sql("UPDATE `task` SET `progress`=1 WHERE `id`=%s", (parse_task,))
    sql("UPDATE `document` SET `run`='3', `chunk_num`=6 WHERE `id`=%s", (doc_id,))
    models.add_models(world.settings.llm, world.owner.tenant_id, "OpenAI-API-Compatible", "default", [models.NewModel("fake-raptor", "chat", None, 8192)])
    models.set_defaults(world.owner.tenant_id, chat=ModelRef("fake-raptor", "default", "OpenAI-API-Compatible"))
    sql("UPDATE `knowledgebase` SET `parser_config`=%s WHERE `id`=%s", (json.dumps({"raptor": True}), world.dataset.id))
    class Queue:
        def __init__(self): self.task = None
        def ping(self): pass
        def enqueue(self, task_id, digest, priority=0): self.task = task_id; return "1"
    queue = Queue()
    principal = principal_of(world.owner)
    started = jobs.start_job(world.settings, principal, world.dataset.id, "raptor", queue=queue)
    child = task_service.load_dataset_job_context(queue.task)
    assert child is not None and child.doc_id == doc_id
    fake.chat_responses[:] = [f"Pair {i}: two inspections agree on lighthouse height 52 metres and calibration offset 73 units." for i in range(3)] + ["All six inspections agree on a 52 metre lighthouse and a 73 unit calibration offset."]
    result = run_raptor(child, TaskControl(), world.deps())
    assert len(result.chunk_ids) == 4
    task_service.mark_task_done(child.task_id, result.chunk_ids, 0.1)
    jobs.settle(child.job_id)
    indexed_rows = indexed(world, doc_id=[doc_id])
    summaries = [row for row in indexed_rows if row.get("origin_kwd") == "raptor"]
    assert [sum(row["raptor_level_int"] == level for row in summaries) for level in (1, 2)] == [3, 1]
    assert set(summaries[-1]["raptor_leaf_ids_kwd"]) == {row["id"] for row in leaves}
    assert "All six inspections" in summaries[-1]["content_with_weight"]
    assert visible_summaries(summaries, world.store(), world.owner.tenant_id, [world.dataset.id])
    body = {"question": "lighthouse height", "dataset_ids": [world.dataset.id], "similarity_threshold": 0}
    view = retrieval_service.search(principal, scope_of(world), body, world.embed_settings, doc_store=world.store(), embedder=lambda _: [1.0] * 8)
    retrieved = [row for row in view["chunks"] if row.get("summary_level")]
    assert retrieved and all(row["source_leaves"] for row in retrieved)
    assert all(leaf["doc_id"] == doc_id for row in retrieved for leaf in row["source_leaves"])
    sql("UPDATE `document` SET `status`='0' WHERE `id`=%s", (doc_id,))
    hidden = retrieval_service.search(principal, scope_of(world), body, world.embed_settings, doc_store=world.store(), embedder=lambda _: [1.0] * 8)
    assert not any(row.get("summary_level") for row in hidden["chunks"])
