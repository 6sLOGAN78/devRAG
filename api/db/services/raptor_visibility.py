"""Read-time authorization for completed RAPTOR summaries and their real leaves."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from api.db.database import DB
from api.db.models import DatasetJob, Document, Task
from api.db.services.chunk_view import chunk_view_fields
from common.doc_store.doc_store_base import DocStoreConnection, index_name

MAX_CANDIDATES = 64
MAX_LEAVES_PER_SUMMARY = 200
MAX_LOOKUP_LEAVES = 2000


def visible_summaries(rows: list[dict[str, Any]], store: DocStoreConnection, tenant_id: str,
                      dataset_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Reject a summary unless its job and every original source leaf remain current."""
    if len(rows) > MAX_CANDIDATES:
        return {}
    candidates: dict[str, tuple[dict[str, Any], list[str]]] = {}
    wanted_jobs = set()
    for row in rows:
        chunk_id, job_id, doc_id = row.get("id"), row.get("raptor_job_id_kwd"), row.get("doc_id")
        leaves = row.get("raptor_leaf_ids_kwd")
        if not isinstance(chunk_id, str) or not isinstance(job_id, str) or not isinstance(doc_id, str) or not isinstance(leaves, list) or not 2 <= len(leaves) <= MAX_LEAVES_PER_SUMMARY:
            continue
        if any(not isinstance(leaf, str) or not leaf or len(leaf) > 128 for leaf in leaves) or len(set(leaves)) != len(leaves):
            continue
        if row.get("kb_id") not in dataset_ids or row.get("raptor_level_int") not in {1, 2, 3}:
            continue
        candidates[chunk_id] = (row, leaves)
        wanted_jobs.add(job_id)
    if not candidates:
        return {}
    with DB.connection_context():
        jobs = {job.id: job for job in DatasetJob.select().where(DatasetJob.id.in_(wanted_jobs))}
        wanted_docs = {source.get("id") for job in jobs.values() for source in (job.snapshot if isinstance(job.snapshot, list) else [])
                       if isinstance(source, dict) and isinstance(source.get("id"), str)}
        docs = {doc.id: doc for doc in Document.select().where(Document.id.in_(wanted_docs))}
        latest = {}
        for job in DatasetJob.select(DatasetJob.id, DatasetJob.kb_id, DatasetJob.create_time).where(
                (DatasetJob.kb_id.in_(dataset_ids)) & (DatasetJob.job_type == "raptor") & (DatasetJob.status == "done")
        ).order_by(DatasetJob.create_time.desc(), DatasetJob.id.desc()):
            latest.setdefault(job.kb_id, job.id)
        parse_tasks = defaultdict(list)
        for task in Task.select(Task.id, Task.doc_id).where((Task.doc_id.in_(wanted_docs)) & (Task.task_type == "parse")).order_by(Task.id):
            parse_tasks[task.doc_id].append(task.id)
    valid: dict[str, tuple[dict[str, Any], list[str], set[str]]] = {}
    for chunk_id, (row, leaves) in candidates.items():
        job = jobs.get(row["raptor_job_id_kwd"])
        if job is None or job.job_type != "raptor" or job.status != "done" or job.tenant_id != tenant_id or job.kb_id != row["kb_id"]:
            continue
        if latest.get(job.kb_id) != job.id or row.get("raptor_generation_kwd") != job.digest:
            continue
        snapshot = job.snapshot if isinstance(job.snapshot, list) else []
        if not snapshot or len(snapshot) > 64:
            continue
        source_ids = set()
        for source in snapshot:
            if not isinstance(source, dict) or not isinstance(source.get("id"), str) or source["id"] in source_ids:
                break
            doc = docs.get(source["id"])
            if doc is None or doc.kb_id != job.kb_id or doc.status != "1" or doc.run == "1" or source.get("hash") != (doc.content_hash or "") or source.get("source_tasks") != parse_tasks[doc.id]:
                break
            source_ids.add(doc.id)
        else:
            if row["doc_id"] in source_ids:
                valid[chunk_id] = (row, leaves, source_ids)
    by_dataset: dict[str, set[str]] = defaultdict(set)
    for row, leaves, _ in valid.values():
        by_dataset[row["kb_id"]].update(leaves)
    if sum(len(items) for items in by_dataset.values()) > MAX_LOOKUP_LEAVES:
        return {}
    leaf_rows: dict[tuple[str, str], dict[str, Any]] = {}
    for dataset_id, ids in by_dataset.items():
        fetched = store.search(["doc_id", "kb_id", "docnm_kwd", "content_with_weight", "position_int", "page_num_int", "page_dims_flt",
                                "available_int", "doc_enabled_int", "origin_kwd"], [], {"id": sorted(ids)}, [], None, 0,
                               len(ids), index_name(tenant_id), [dataset_id])
        for leaf in fetched.hits:
            leaf_rows[(dataset_id, str(leaf.get("id")))] = leaf
    result = {}
    for chunk_id, (row, leaves, source_ids) in valid.items():
        source_rows = [leaf_rows.get((row["kb_id"], leaf_id)) for leaf_id in leaves]
        if any(leaf is None or leaf.get("doc_id") not in source_ids or leaf.get("kb_id") != row["kb_id"] or leaf.get("origin_kwd") == "raptor"
               or leaf.get("available_int") != 1 or leaf.get("doc_enabled_int") != 1 or not isinstance(leaf.get("content_with_weight"), str) for leaf in source_rows):
            continue
        result[chunk_id] = [
            {"chunk_id": str(leaf["id"]), "doc_id": str(leaf["doc_id"]), "doc_name": str(leaf.get("docnm_kwd") or ""),
             "dataset_id": str(leaf["kb_id"]), "content": leaf["content_with_weight"][:512], **chunk_view_fields(leaf)}
            for leaf in source_rows
        ]
    return result


def current_reference_summaries(chunks: list[dict[str, Any]], tenant_id: str) -> dict[str, list[dict[str, Any]]]:
    """Recheck a stored chat reference; stale summary text must be redacted."""
    from common.settings import get_settings
    from rag.utils.es_conn import get_doc_store

    wanted: dict[str, set[str]] = defaultdict(set)
    for chunk in chunks[:MAX_CANDIDATES]:
        if isinstance(chunk.get("chunk_id"), str) and isinstance(chunk.get("dataset_id"), str):
            wanted[chunk["dataset_id"]].add(chunk["chunk_id"])
    if sum(len(ids) for ids in wanted.values()) > MAX_CANDIDATES:
        return {}
    store = get_doc_store(get_settings())
    rows = []
    for dataset_id, ids in wanted.items():
        fetched = store.search(["doc_id", "kb_id", "origin_kwd", "raptor_job_id_kwd", "raptor_generation_kwd",
                                "raptor_level_int", "raptor_leaf_ids_kwd"], [], {"id": sorted(ids)}, [], None, 0,
                               len(ids), index_name(tenant_id), [dataset_id])
        rows.extend(row for row in fetched.hits if row.get("origin_kwd") == "raptor")
    return visible_summaries(rows, store, tenant_id, list(wanted))
