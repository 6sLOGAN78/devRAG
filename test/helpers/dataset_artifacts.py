"""Seed an owned RAPTOR artifact with current original leaves for route matrices."""
from __future__ import annotations

import hashlib
import json
import uuid


def owned_artifact(world) -> str:
    from api.db.database import DB
    from api.db.models import DatasetJob, Document, DocumentAsset, Task
    from common.constants import BUCKET_NAME
    from common.doc_store.doc_store_base import index_name
    from common.settings import load_settings
    from rag.utils.es_conn import get_doc_store
    from rag.utils.storage_factory import get_storage

    cached = world.scratch.get("matrix_artifact")
    if cached:
        with DB.connection_context():
            asset = DocumentAsset.get_or_none(DocumentAsset.id == cached[:-5])
            job = DatasetJob.get_or_none(DatasetJob.id == asset.generation_id) if asset else None
        if job is not None and job.status == "done":
            return cached
    dataset_id = str(world.a_team_dataset["id"])
    doc_id = str(world.a_parsed_document["id"])
    settings = load_settings()
    fetched = get_doc_store(settings).search(
        ["id", "available_int", "doc_enabled_int", "origin_kwd"], [],
        {"id": world.a_parsed_chunks}, [], None, 0, len(world.a_parsed_chunks),
        index_name(world.a.tenant_id), [dataset_id],
    )
    leaves = sorted(str(row["id"]) for row in fetched.hits if row.get("available_int") == 1
                    and row.get("doc_enabled_int") == 1 and row.get("origin_kwd") != "raptor")[:2]
    assert len(leaves) == 2, "matrix source needs two current original leaves"
    with DB.connection_context():
        doc = Document.get_by_id(doc_id)
        tasks = [task.id for task in Task.select(Task.id).where((Task.doc_id == doc_id) & (Task.task_type == "parse")).order_by(Task.id)]
        if not tasks:
            task_id = uuid.uuid4().hex
            Task.create(id=task_id, doc_id=doc_id, task_type="parse", progress=1)
            tasks = [task_id]
        job_id = uuid.uuid4().hex
        digest = "0" * 64
        DatasetJob.create(id=job_id, tenant_id=world.a.tenant_id, kb_id=dataset_id,
                          created_by=world.a.user_id, job_type="raptor", status="done",
                          digest=digest, generation=job_id,
                          snapshot=[{"id": doc_id, "hash": doc.content_hash or "", "source_tasks": tasks}],
                          config={"raptor": True}, total=1, progress_msg="Completed.")
    identifier = hashlib.sha256(f"raptor-artifact:{job_id}".encode()).hexdigest()[:32]
    filename = f"{identifier}.json"
    key = f"tenant/{world.a.tenant_id}/dataset/{dataset_id}/raptor/{job_id}.json"
    content = json.dumps({"schema_version": 1, "generation": job_id,
                          "summaries": [{"text": "matrix alpha and beta", "source_leaf_ids": leaves}]}).encode()
    get_storage(settings).put(BUCKET_NAME, key, content)
    with DB.connection_context():
        DocumentAsset.create(id=identifier, tenant_id=world.a.tenant_id, kb_id=dataset_id,
                             doc_id=None, kind="raptor", object_key=key, mime_type="application/json",
                             size=len(content), sha256=hashlib.sha256(content).hexdigest(),
                             generation_id=job_id, caption="", page=None, width=0, height=0,
                             source_manifest=leaves)
    from api.db.services.dataset_artifact_service import read_artifact
    from api.db.services.auth_service import AUTH_JWT, Principal
    assert read_artifact(settings, Principal(world.a.user_id, world.a.tenant_id, "owner", AUTH_JWT, False), filename) == content
    world.scratch["matrix_artifact"] = filename
    return filename
