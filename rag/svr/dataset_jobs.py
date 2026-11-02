"""Refresh bounded enrichment on existing source chunks without reparsing or reembedding."""
from __future__ import annotations

import json
import math

from api.db.database import DB, transaction
from api.db.models import DatasetJob, Document, Task
from api.db.models.base import current_timestamp_ms, timestamp_to_date
from api.db.services import dataset_job_service, document_metadata_service, task_service, tenant_model_service
from api.db.services.task_service import TaskContext
from common.doc_store.doc_store_base import OrderByExpr, index_name
from rag.nlp.tokenizer import tokenize
from rag.svr.control import TaskCancelled, TaskControl
from rag.svr.embedding import release_database_connection
from rag.svr.enrichment import ENRICHMENT_BATCH, MAX_ENRICHED_CHUNKS, EnrichedFeatures, parse_generated_metadata
from rag.svr.failure import TaskFailure
from rag.svr.pipeline import PipelineDeps, PipelineResult


def _current(child: dataset_job_service.DatasetChild, control: TaskControl) -> None:
    control.check()
    fresh = dataset_job_service.load_child(child.task_id)
    if fresh is None or fresh.digest != child.digest or fresh.job_id != child.job_id:
        raise TaskCancelled("dataset job changed")


def _task_context(child: dataset_job_service.DatasetChild) -> TaskContext:
    with DB.connection_context():
        doc = Document.get_or_none((Document.id == child.doc_id) & (Document.kb_id == child.dataset_id))
    if doc is None:
        raise TaskCancelled("document deleted")
    return TaskContext(child.task_id, doc.id, child.dataset_id, child.tenant_id, 0, 1, child.digest, 0,
                       doc.name or "", doc.suffix or "", doc.location or "", int(doc.size or 0), "1", doc.status or "1",
                       doc.content_hash or "", doc.parser_id, child.config, "", doc.created_by, meta_fields=dict(doc.meta_fields or {}))


def _publish_metadata(child: dataset_job_service.DatasetChild, values: dict) -> dict:
    generated = document_metadata_service.validate_metadata(values)
    with DB.connection_context(), transaction():
        job = DatasetJob.select(DatasetJob.status).where(DatasetJob.id == child.job_id).for_update().first()
        doc = Document.select(Document.meta_fields, Document.content_hash, Document.status, Document.run).where(
            (Document.id == child.doc_id) & (Document.kb_id == child.dataset_id)).for_update().first()
        valid = (
            job is not None and job.status == "running" and doc is not None and doc.status == "1" and doc.run != "1"
            and (doc.content_hash or "") == child.content_hash
            and Task.select(Task.id).where((Task.id == child.task_id) & (Task.doc_id == child.job_id)).exists()
        )
        if not valid:
            raise TaskCancelled("dataset job changed before metadata publication")
        stored = dict(doc.meta_fields or {})
        human = document_metadata_service._current_user_fields(stored)
        candidate = {**human, "_generated": generated,
                     "_provenance": {key: f"generated:0000000000:{child.task_id}" for key in generated}}
        document_metadata_service.validate_metadata({**generated, **human})
        if len(json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()) > document_metadata_service.MAX_BYTES:
            raise TaskFailure("embed", "file_too_large")
        now = current_timestamp_ms()
        Document.update(meta_fields=candidate, update_time=now, update_date=timestamp_to_date(now)).where(Document.id == child.doc_id).execute()
    return candidate


def run_refresh(child: dataset_job_service.DatasetChild, control: TaskControl, deps: PipelineDeps) -> PipelineResult:
    _current(child, control)
    ctx = _task_context(child)
    config = child.config
    name = index_name(child.tenant_id)
    condition = {"doc_id": child.doc_id, "must_not": {"removed_kwd": "Y"}}
    store = deps.doc_store
    result = store.search(["id", "content_with_weight", "tags_source_kwd", "tag_feas", "tags_kwd", "meta_fields_list", "generated_questions_kwd", "important_kwd", "question_tks"],
                          [], condition, [], OrderByExpr().asc("id"), 0, MAX_ENRICHED_CHUNKS + 1, name, [child.dataset_id])
    if result.total < 1 or result.total > MAX_ENRICHED_CHUNKS or len(result.hits) != result.total:
        raise TaskFailure("embed", "file_too_large" if result.total > MAX_ENRICHED_CHUNKS else "no_readable_text")
    rows = result.hits
    texts = [row.get("content_with_weight") for row in rows]
    if any(not isinstance(text, str) or not text.strip() for text in texts):
        raise TaskFailure("embed", "no_readable_text")
    release_database_connection()
    enriched = [EnrichedFeatures() for _ in rows]
    keyword_count, question_count = config.get("auto_keywords", 0), config.get("auto_questions", 0)
    if keyword_count or question_count:
        if type(keyword_count) is not int or not 0 <= keyword_count <= 32 or type(question_count) is not int or not 0 <= question_count <= 16:
            raise TaskFailure("embed", "provider_refused")
        model_id = tenant_model_service.get_defaults(child.tenant_id).chat
        if not model_id:
            raise TaskFailure("embed", "model_unavailable")
        for start in range(0, len(rows), ENRICHMENT_BATCH):
            _current(child, control)
            batch = deps.embedder.enrich(texts[start:start + ENRICHMENT_BATCH], model_id, keyword_count, question_count, ctx, control)
            enriched[start:start + len(batch)] = batch
    labels = None
    if config.get("auto_tags"):
        allowed, model_id = config.get("allowed_tags"), config.get("tag_model_id")
        if not isinstance(allowed, list) or not allowed or not isinstance(model_id, str) or not model_id:
            raise TaskFailure("embed", "model_unavailable")
        labels = []
        for start in range(0, len(rows), ENRICHMENT_BATCH):
            _current(child, control)
            labels.extend(deps.embedder.generate_tags(texts[start:start + ENRICHMENT_BATCH], model_id, allowed, ctx, control))
    metadata = None
    if config.get("auto_metadata"):
        schema, model_id = config.get("metadata_schema"), config.get("metadata_model_id")
        if not isinstance(schema, list) or not schema or not isinstance(model_id, str) or not model_id:
            raise TaskFailure("embed", "model_unavailable")
        values = {}
        for start in range(0, len(rows), ENRICHMENT_BATCH):
            _current(child, control)
            values.update(deps.embedder.generate_metadata(texts[start:start + ENRICHMENT_BATCH], model_id, schema, ctx, control))
        parse_generated_metadata(json.dumps({"metadata": values}, ensure_ascii=False), schema)
        metadata = values
    for i, row in enumerate(rows):
        _current(child, control)
        fields = {}
        if keyword_count or question_count:
            fields["important_kwd"] = list(enriched[i].keywords)
            fields["important_tks"] = " ".join(tokenize(" ".join(enriched[i].keywords)))
            fields["generated_questions_kwd"] = list(enriched[i].questions)
            fields["question_tks"] = " ".join(tokenize(" ".join(enriched[i].questions)))
        if labels is not None:
            weight = 1 / math.sqrt(len(labels[i])) if labels[i] else 0
            fields.update({"tag_feas": {label: weight for label in labels[i]}, "tags_kwd": list(labels[i]), "tags_source_kwd": "generated"})
        if fields and not store.update({"id": row["id"], "doc_id": child.doc_id}, fields, name, child.dataset_id):
            raise TaskFailure("index", "index_unavailable")
        task_service.set_progress(child.task_id, (i + 1) / (len(rows) + 1), f"Refreshed {i + 1} of {len(rows)} chunks.")
    if metadata is not None:
        _current(child, control)
        stored = _publish_metadata(child, metadata)
        if not store.update({"doc_id": child.doc_id}, {document_metadata_service.INDEX_FIELD: json.dumps(stored, ensure_ascii=False, sort_keys=True, separators=(",", ":"))}, name, child.dataset_id):
            raise TaskFailure("index", "index_unavailable")
    deps.embedder.forget(child.task_id)
    return PipelineResult(tuple(row["id"] for row in rows), len(rows), 0, 0, 0)
