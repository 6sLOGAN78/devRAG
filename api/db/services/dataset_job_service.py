"""Owned, bounded dataset enrichment runs backed by ordinary stream tasks."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any

from api.db.database import DB, transaction
from api.db.models import DatasetJob, Document, Knowledgebase, Task
from api.db.models.base import current_timestamp_ms, timestamp_to_date
from api.db.services.auth_service import Principal
from api.db.services.knowledgebase_service import load_visible_dataset
from api.db.services.service_errors import Kind, ServiceError
from api.db.services.tenant_scope import can_manage_dataset
from api.db.services import tenant_model_service
from api.utils import reasons
from common.settings import Settings
from rag.queue.factory import get_queue
from rag.queue.queue_base import QueueUnavailable, TaskQueue

logger = logging.getLogger(__name__)
MAX_JOB_DOCUMENTS = 64
MAX_JOB_CHUNKS = 256
JOB_TYPE = "enrich"
TASK_TYPE = "dataset_enrich"
RAPTOR_TASK_TYPE = "dataset_raptor"
JOB_TASK_TYPES = {TASK_TYPE, RAPTOR_TASK_TYPE}
_ID = re.compile(r"[0-9a-f]{32}\Z")


def _not_found() -> ServiceError:
    return ServiceError(Kind.NOT_FOUND, reasons.DATASET_NOT_FOUND, "not found")


def _invalid(message: str) -> ServiceError:
    return ServiceError(Kind.INVALID, reasons.PARSER_CONFIG_INVALID, message)


def _stamp() -> dict[str, Any]:
    now = current_timestamp_ms()
    return {"update_time": now, "update_date": timestamp_to_date(now)}


def _digest(snapshot: list[dict[str, Any]], config: dict[str, Any]) -> str:
    payload = json.dumps({"documents": snapshot, "config": config}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def _config(raw: object, job_type: str = JOB_TYPE) -> dict[str, Any]:
    config = dict(raw) if isinstance(raw, dict) else {}
    if job_type == "raptor":
        if config.get("raptor") is not True:
            raise _invalid("enable RAPTOR in dataset settings before starting")
        return config
    if not (config.get("auto_keywords") or config.get("auto_questions") or config.get("auto_tags") or config.get("auto_metadata")):
        raise _invalid("enable automatic enrichment in dataset settings before starting")
    return config


def _owned(principal: Principal, dataset_id: str):
    visible = load_visible_dataset(principal, dataset_id)
    if not can_manage_dataset(visible.dataset.created_by, principal.user_id, visible.scope.role):
        raise ServiceError(Kind.FORBIDDEN, reasons.FORBIDDEN, "forbidden")
    return visible


def _job(principal: Principal, dataset_id: str, job_id: str) -> DatasetJob:
    load_visible_dataset(principal, dataset_id)
    if not isinstance(job_id, str) or _ID.fullmatch(job_id) is None:
        raise _not_found()
    with DB.connection_context():
        row = DatasetJob.get_or_none((DatasetJob.id == job_id) & (DatasetJob.kb_id == dataset_id))
    if row is None:
        raise _not_found()
    return row


def _view(row: DatasetJob) -> dict[str, Any]:
    with DB.connection_context():
        tasks = list(Task.select(Task.progress).where((Task.doc_id == row.id) & (Task.task_type.in_(JOB_TASK_TYPES))))
    done = sum(t.progress is not None and t.progress >= 1 for t in tasks)
    failed = sum(t.progress is not None and t.progress < 0 for t in tasks)
    total = int(row.total)
    status = row.status
    if status == "running" and len(tasks) != total:
        status = "failed"
    elif status == "running" and done + failed == total:
        status = "failed" if failed else "done"
    run = {"running": "1", "cancelled": "2", "done": "3", "failed": "4"}[status]
    return {"id": row.id, "type": row.job_type, "run": run, "total": total, "completed": done,
            "failed": failed, "progress": (done + failed) / total if total else 1.0,
            "created_at": int(row.create_time), "updated_at": int(row.update_time)}


def start_job(settings: Settings, principal: Principal, dataset_id: str, job_type: str, *, queue: TaskQueue | None = None) -> dict[str, Any]:
    visible = _owned(principal, dataset_id)
    if job_type not in {JOB_TYPE, "raptor"}:
        raise _invalid("this dataset job type is not available")
    config = _config(visible.dataset.parser_config, job_type)
    if job_type == "raptor":
        chat_model = tenant_model_service.get_defaults(visible.scope.tenant_id).chat
        if not chat_model:
            raise ServiceError(Kind.CONFLICT, reasons.MODEL_UNAVAILABLE, "choose a chat model in workspace settings")
        config = {**config, "raptor_model_id": chat_model, "embedding_model_id": visible.dataset.embd_id}
    jobs = queue if queue is not None else get_queue(settings)
    try:
        jobs.ping()
    except QueueUnavailable:
        raise ServiceError(Kind.UNAVAILABLE, reasons.QUEUE_UNAVAILABLE, "the task queue is unavailable") from None
    reconcile_running_jobs()
    with DB.connection_context(), transaction():
        kb = Knowledgebase.select().where((Knowledgebase.id == dataset_id) & (Knowledgebase.tenant_id == visible.scope.tenant_id) & (Knowledgebase.status == "1")).for_update().first()
        if kb is None:
            raise _not_found()
        if DatasetJob.select().where((DatasetJob.kb_id == dataset_id) & (DatasetJob.status == "running")).exists():
            raise ServiceError(Kind.CONFLICT, reasons.ALREADY_RUNNING, "a dataset job is already running")
        docs = list(Document.select(Document.id, Document.content_hash, Document.run, Document.chunk_num).where(
            (Document.kb_id == dataset_id) & (Document.status == "1") & (Document.chunk_num > 0)
        ).order_by(Document.id).limit(MAX_JOB_DOCUMENTS + 1))
        if not docs:
            raise _invalid("this dataset has no indexed documents to refresh")
        if len(docs) > MAX_JOB_DOCUMENTS:
            raise _invalid("this dataset has too many documents for one enrichment run")
        total_chunks = sum(int(doc.chunk_num or 0) for doc in docs)
        if total_chunks > (200 if job_type == "raptor" else MAX_JOB_CHUNKS):
            raise _invalid("this dataset has too many chunks for one enrichment run")
        if job_type == "raptor" and total_chunks < 2:
            raise _invalid("RAPTOR needs at least two indexed source chunks")
        if any(doc.run == "1" for doc in docs):
            raise ServiceError(Kind.CONFLICT, reasons.ALREADY_RUNNING, "wait for document parsing to finish")
        parse_rows = list(Task.select(Task.id, Task.doc_id).where((Task.doc_id.in_([doc.id for doc in docs])) & (Task.task_type == "parse")).order_by(Task.id))
        if len(parse_rows) > 1024:
            raise _invalid("this dataset has too many source tasks for one enrichment run")
        by_doc: dict[str, list[str]] = {doc.id: [] for doc in docs}
        for task in parse_rows:
            by_doc[task.doc_id].append(task.id)
        snapshot = [{"id": doc.id, "hash": doc.content_hash or "", "source_tasks": by_doc[doc.id]} for doc in docs]
        digest = _digest(snapshot, config)
        job_id = uuid.uuid4().hex
        DatasetJob.create(id=job_id, tenant_id=kb.tenant_id, kb_id=dataset_id, created_by=principal.user_id,
                          job_type=job_type, status="running", generation=uuid.uuid4().hex, digest=digest,
                          snapshot=snapshot, config=config, total=1 if job_type == "raptor" else len(snapshot),
                          progress_msg="Queued RAPTOR generation." if job_type == "raptor" else "Queued enrichment refresh.")
        pending = []
        for index, doc in enumerate(snapshot[:1] if job_type == "raptor" else snapshot):
            task_id = hashlib.sha256(f"{job_id}:{index}".encode()).hexdigest()[:32]
            task_digest = hashlib.sha256(f"{digest}:{doc['id']}:{index}".encode()).hexdigest()
            Task.create(id=task_id, doc_id=job_id, from_page=index, to_page=index + 1,
                        task_type=TASK_TYPE if job_type == JOB_TYPE else RAPTOR_TASK_TYPE, digest=task_digest, progress=0.0, retry_count=0)
            pending.append((task_id, task_digest))
    for task_id, task_digest in pending:
        try:
            jobs.enqueue(task_id, task_digest, 0)
        except QueueUnavailable:
            logger.warning("dataset job publish interrupted", extra={"job": job_id})
            # The worker reconciler republishes unfinished child rows; a partial enqueue is safe.
            break
    return get_job(principal, dataset_id, job_id)


def list_jobs(principal: Principal, dataset_id: str) -> dict[str, Any]:
    load_visible_dataset(principal, dataset_id)
    with DB.connection_context():
        rows = list(DatasetJob.select().where(DatasetJob.kb_id == dataset_id).order_by(DatasetJob.create_time.desc()).limit(20))
    return {"items": [_view(row) for row in rows]}


def get_job(principal: Principal, dataset_id: str, job_id: str) -> dict[str, Any]:
    return _view(_job(principal, dataset_id, job_id))


def cancel_job(principal: Principal, dataset_id: str, job_id: str) -> dict[str, Any]:
    _owned(principal, dataset_id)
    row = _job(principal, dataset_id, job_id)
    with DB.connection_context(), transaction():
        DatasetJob.update(status="cancelled", progress_msg="Cancelled by member.", **_stamp()).where((DatasetJob.id == row.id) & (DatasetJob.status == "running")).execute()
    return get_job(principal, dataset_id, job_id)


@dataclass(frozen=True)
class DatasetChild:
    task_id: str
    job_id: str
    doc_id: str
    dataset_id: str
    tenant_id: str
    digest: str
    job_digest: str
    config: dict[str, Any]
    content_hash: str
    index: int
    source_doc_ids: tuple[str, ...]


def load_child(task_id: str) -> DatasetChild | None:
    """Resolve the real document only from an owned snapshot; never look up the sentinel as Document."""
    with DB.connection_context():
        task = Task.get_or_none((Task.id == task_id) & (Task.task_type.in_(JOB_TASK_TYPES)))
        if task is None:
            return None
        job = DatasetJob.get_or_none((DatasetJob.id == task.doc_id) & (DatasetJob.status == "running"))
        if job is None:
            return None
        if task.task_type != (TASK_TYPE if job.job_type == JOB_TYPE else RAPTOR_TASK_TYPE):
            return None
        snapshot = job.snapshot
        index = int(task.from_page)
        if not isinstance(snapshot, list) or index < 0 or index >= len(snapshot) or int(task.to_page) != index + 1:
            return None
        entry = snapshot[index]
        if not isinstance(entry, dict) or set(entry) != {"id", "hash", "source_tasks"} or not isinstance(entry["id"], str) or not isinstance(entry["source_tasks"], list):
            return None
        kb = Knowledgebase.get_or_none((Knowledgebase.id == job.kb_id) & (Knowledgebase.tenant_id == job.tenant_id) & (Knowledgebase.status == "1"))
        if kb is None or _digest(snapshot, dict(job.config or {})) != job.digest:
            return None
        entries = snapshot if job.job_type == "raptor" else [entry]
        source_ids = []
        for source in entries:
            if not isinstance(source, dict) or set(source) != {"id", "hash", "source_tasks"} or not isinstance(source["id"], str) or not isinstance(source["source_tasks"], list):
                return None
            real = Document.get_or_none((Document.id == source["id"]) & (Document.kb_id == job.kb_id) & (Document.status == "1"))
            if real is None or real.run == "1" or (real.content_hash or "") != source["hash"]:
                return None
            source_tasks = [row.id for row in Task.select(Task.id).where((Task.doc_id == real.id) & (Task.task_type == "parse")).order_by(Task.id)]
            if source_tasks != source["source_tasks"]:
                return None
            source_ids.append(real.id)
        expected_digest = hashlib.sha256(f"{job.digest}:{entry['id']}:{index}".encode()).hexdigest()
        if task.digest != expected_digest:
            return None
        return DatasetChild(task.id, job.id, entry["id"], job.kb_id, job.tenant_id, task.digest, job.digest,
                            dict(job.config or {}), entry["hash"], index, tuple(source_ids))


def settle(job_id: str) -> None:
    with DB.connection_context(), transaction():
        job = DatasetJob.select().where(DatasetJob.id == job_id).for_update().first()
        if job is None or job.status != "running":
            return
        tasks = list(Task.select(Task.progress).where((Task.doc_id == job_id) & (Task.task_type.in_(JOB_TASK_TYPES))))
        if len(tasks) != job.total or any(task.progress is None or 0 <= task.progress < 1 for task in tasks):
            return
        failed = any(task.progress < 0 for task in tasks)
        DatasetJob.update(
            status="failed" if failed else "done",
            progress_msg="One or more documents failed." if failed else "Enrichment refreshed.",
            **_stamp(),
        ).where(DatasetJob.id == job_id).execute()


def fail_stale_child(task_id: str) -> None:
    """A replaced/deleted source closes its job instead of leaving a running slot forever."""
    with DB.connection_context():
        task = Task.get_or_none((Task.id == task_id) & (Task.task_type.in_(JOB_TASK_TYPES)))
        if task is None:
            return
        job_id = task.doc_id
        job = DatasetJob.get_or_none((DatasetJob.id == job_id) & (DatasetJob.status == "running"))
    if job is not None:
        from api.db.services.task_service import mark_task_failed

        mark_task_failed(task_id, "source: dataset job source changed")
        settle(job_id)


def settle_for_child(task_id: str) -> None:
    with DB.connection_context():
        task = Task.select(Task.doc_id).where((Task.id == task_id) & (Task.task_type.in_(JOB_TASK_TYPES))).first()
    if task is not None:
        settle(task.doc_id)


def pending_children(limit: int = 64) -> list[tuple[str, str]]:
    with DB.connection_context():
        rows = (Task.select(Task.id, Task.digest).join(DatasetJob, on=(Task.doc_id == DatasetJob.id))
                .where((Task.task_type.in_(JOB_TASK_TYPES)) & (Task.progress >= 0) & (Task.progress < 1) &
                       (Task.update_time < current_timestamp_ms() - 60_000) & (DatasetJob.status == "running"))
                .order_by(Task.create_time).limit(limit))
        return [(row.id, row.digest or "") for row in rows]


def reconcile_running_jobs(limit: int = 20) -> None:
    """Close orphaned or stale generations after document/dataset changes or a worker outage."""
    with DB.connection_context():
        rows = list(DatasetJob.select(DatasetJob.id, DatasetJob.total).where(DatasetJob.status == "running").order_by(DatasetJob.create_time).limit(limit))
    for job in rows:
        with DB.connection_context():
            tasks = list(Task.select(Task.id, Task.progress).where((Task.doc_id == job.id) & (Task.task_type.in_(JOB_TASK_TYPES))))
        if len(tasks) != job.total:
            with DB.connection_context():
                DatasetJob.update(status="failed", progress_msg="A source document changed.", **_stamp()).where(
                    (DatasetJob.id == job.id) & (DatasetJob.status == "running")).execute()
            continue
        for task in tasks:
            if task.progress is not None and 0 <= task.progress < 1 and load_child(task.id) is None:
                fail_stale_child(task.id)
        settle(job.id)
