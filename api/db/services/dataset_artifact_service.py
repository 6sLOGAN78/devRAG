"""Owned RAPTOR artifact publication, download and derived-only deletion."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from api.db.database import DB, transaction
from api.db.models import DatasetAlteration, DatasetJob, DocumentAsset
from api.db.services import dataset_job_service, knowledgebase_service as datasets
from api.db.services.auth_service import Principal
from api.db.services.raptor_visibility import visible_summaries
from api.db.services.service_errors import Kind, ServiceError
from api.utils import reasons
from common.constants import BUCKET_NAME
from common.doc_store.doc_store_base import DocStoreConnection, DocStoreError, index_name
from common.settings import Settings
from rag.utils.es_conn import get_doc_store
from rag.utils.storage_base import Storage, StorageError, StorageNotFound
from rag.utils.storage_factory import get_storage

_FILENAME = re.compile(r"([0-9a-f]{32})\.json\Z")
MAX_ARTIFACT_BYTES = 1024 * 1024
MAX_HISTORY_PAGE = 100
MAX_HISTORY_SIZE = 50


def _missing() -> ServiceError:
    return ServiceError(Kind.NOT_FOUND, reasons.DATASET_NOT_FOUND, "not found")


def _artifact_id(job_id: str) -> str:
    return hashlib.sha256(f"raptor-artifact:{job_id}".encode()).hexdigest()[:32]


def _object_key(tenant_id: str, dataset_id: str, job_id: str) -> str:
    return f"tenant/{tenant_id}/dataset/{dataset_id}/raptor/{job_id}.json"


def _audit(tenant_id: str, dataset_id: str, actor_id: str, generation: str,
           status: str, deleted_count: int) -> None:
    import uuid

    DatasetAlteration.create(id=uuid.uuid4().hex, tenant_id=tenant_id, kb_id=dataset_id,
                             actor_id=actor_id, index_type="raptor", generation_id=generation,
                             status=status, deleted_count=deleted_count)


def persist_raptor_artifact(settings: Settings, child: dataset_job_service.DatasetChild,
                            summaries: list[dict[str, Any]], leaf_ids: list[str], *,
                            storage: Storage | None = None) -> str:
    """Save one bounded generated artifact under a server-derived key and ID."""
    if not 1 <= len(summaries) <= 64 or not 2 <= len(leaf_ids) <= 200 or len(set(leaf_ids)) != len(leaf_ids):
        raise ValueError("invalid RAPTOR artifact manifest")
    payload = {"schema_version": 1, "dataset_id": child.dataset_id, "generation": child.job_id,
               "summaries": [{"id": row["id"], "level": row["raptor_level_int"],
                              "text": row["content_with_weight"], "source_leaf_ids": row["raptor_leaf_ids_kwd"]}
                             for row in summaries]}
    content = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    if len(content) > MAX_ARTIFACT_BYTES:
        raise ValueError("RAPTOR artifact is too large")
    identifier = _artifact_id(child.job_id)
    key = _object_key(child.tenant_id, child.dataset_id, child.job_id)
    blobs = storage if storage is not None else get_storage(settings)
    blobs.put(BUCKET_NAME, key, content)
    try:
        with DB.connection_context(), transaction():
            job = DatasetJob.select().where((DatasetJob.id == child.job_id) & (DatasetJob.status == "running")).for_update().first()
            if job is None or job.digest != child.job_digest:
                raise ValueError("RAPTOR generation changed")
            values = dict(tenant_id=child.tenant_id, kb_id=child.dataset_id, doc_id=None,
                          kind="raptor", object_key=key, mime_type="application/json", size=len(content),
                          sha256=hashlib.sha256(content).hexdigest(), generation_id=child.job_id,
                          caption="", page=None, width=0, height=0, source_manifest=sorted(leaf_ids))
            previous = DocumentAsset.get_or_none(DocumentAsset.id == identifier)
            if previous:
                DocumentAsset.update(**values).where(DocumentAsset.id == identifier).execute()
            else:
                DocumentAsset.create(id=identifier, **values)
    except BaseException:
        from api.db.services.file_service import release_blobs

        release_blobs(blobs, [key], "RAPTOR artifact publication")
        raise
    return f"{identifier}.json"


def list_alterations(principal: Principal, dataset_id: str, *, page: int = 1,
                     size: int = 20) -> dict[str, Any]:
    visible = datasets.load_visible_dataset(principal, dataset_id)
    if type(page) is not int or not 1 <= page <= MAX_HISTORY_PAGE or type(size) is not int or not 1 <= size <= MAX_HISTORY_SIZE:
        raise ServiceError(Kind.INVALID, reasons.PARSER_CONFIG_INVALID, "invalid history page")
    with DB.connection_context():
        query = DatasetAlteration.select().where((DatasetAlteration.tenant_id == visible.scope.tenant_id) &
                                                 (DatasetAlteration.kb_id == dataset_id))
        total = query.count()
        rows = list(query.order_by(DatasetAlteration.create_time.desc(), DatasetAlteration.id.desc())
                    .paginate(page, size))
    return {"items": [{"actor": row.actor_id, "type": row.index_type,
                       "generation": row.generation_id, "outcome": row.status,
                       "time": int(row.create_time), "deleted_count": int(row.deleted_count)} for row in rows],
            "total": total, "page": page, "size": size}


def delete_derived_index(settings: Settings, principal: Principal, dataset_id: str,
                         index_type: str, *, doc_store: DocStoreConnection | None = None,
                         storage: Storage | None = None) -> dict[str, Any]:
    if index_type != "raptor":
        raise _missing()
    visible = dataset_job_service._owned(principal, dataset_id)
    tenant_id = visible.scope.tenant_id
    engine = doc_store if doc_store is not None else get_doc_store(settings)
    blobs = storage if storage is not None else get_storage(settings)
    with datasets._named_lock(datasets.upload_lock_name(dataset_id), 10, "another dataset change is running"):
        dataset_job_service._owned(principal, dataset_id)
        with DB.connection_context(), transaction():
            jobs = list(DatasetJob.select().where((DatasetJob.kb_id == dataset_id) &
                                                  (DatasetJob.tenant_id == tenant_id) &
                                                  (DatasetJob.job_type == "raptor")).order_by(DatasetJob.create_time.desc()))
            generation = jobs[0].id if jobs else ""
            if jobs:
                DatasetJob.update(status="cancelled").where(DatasetJob.id.in_([job.id for job in jobs])).execute()
        try:
            removed = engine.delete({"origin_kwd": "raptor"}, index_name(tenant_id), dataset_id)
        except DocStoreError:
            with DB.connection_context():
                _audit(tenant_id, dataset_id, principal.user_id, generation, "failed", 0)
            raise ServiceError(Kind.UNAVAILABLE, reasons.INDEX_UNAVAILABLE, "the search index is unavailable") from None
        with DB.connection_context(), transaction():
            assets = list(DocumentAsset.select(DocumentAsset.id, DocumentAsset.object_key).where(
                (DocumentAsset.kb_id == dataset_id) & (DocumentAsset.tenant_id == tenant_id) &
                (DocumentAsset.kind == "raptor")))
            if assets:
                DocumentAsset.delete().where(DocumentAsset.id.in_([asset.id for asset in assets])).execute()
            _audit(tenant_id, dataset_id, principal.user_id, generation, "done", removed)
        from api.db.services.file_service import release_blobs

        release_blobs(blobs, [asset.object_key for asset in assets], "RAPTOR deletion")
    return {"type": "raptor", "deleted_count": removed, "artifact_count": len(assets)}


def read_artifact(settings: Settings, principal: Principal, filename: str, *,
                  doc_store: DocStoreConnection | None = None,
                  storage: Storage | None = None) -> bytes:
    match = _FILENAME.fullmatch(filename) if isinstance(filename, str) else None
    if match is None:
        raise _missing()
    with DB.connection_context():
        asset = DocumentAsset.get_or_none((DocumentAsset.id == match[1]) & (DocumentAsset.kind == "raptor"))
    if asset is None or asset.doc_id is not None or asset.mime_type != "application/json" or not 1 <= asset.size <= MAX_ARTIFACT_BYTES:
        raise _missing()
    visible = datasets.load_visible_dataset(principal, asset.kb_id)
    if asset.tenant_id != visible.scope.tenant_id or not isinstance(asset.source_manifest, list):
        raise _missing()
    engine = doc_store if doc_store is not None else get_doc_store(settings)
    def current() -> bool:
        with DB.connection_context():
            job = DatasetJob.get_or_none((DatasetJob.id == asset.generation_id) &
                                         (DatasetJob.kb_id == asset.kb_id) & (DatasetJob.tenant_id == asset.tenant_id))
            exists = DocumentAsset.select().where(DocumentAsset.id == asset.id).exists()
        if job is None or not exists or job.job_type != "raptor" or job.status != "done" or not isinstance(job.snapshot, list) or not job.snapshot:
            return False
        source = job.snapshot[0]
        if not isinstance(source, dict) or not isinstance(source.get("id"), str):
            return False
        synthetic = {"id": asset.id, "doc_id": source["id"], "kb_id": asset.kb_id,
                     "raptor_job_id_kwd": job.id, "raptor_generation_kwd": job.digest,
                     "raptor_level_int": 1, "raptor_leaf_ids_kwd": asset.source_manifest}
        try:
            return asset.id in visible_summaries([synthetic], engine, asset.tenant_id, [asset.kb_id])
        except DocStoreError:
            raise ServiceError(Kind.UNAVAILABLE, reasons.INDEX_UNAVAILABLE, "the search index is unavailable") from None
    if not current():
        raise _missing()
    blobs = storage if storage is not None else get_storage(settings)
    try:
        if blobs.size(BUCKET_NAME, asset.object_key) != asset.size:
            raise _missing()
        content = blobs.get(BUCKET_NAME, asset.object_key)
    except StorageNotFound:
        raise _missing() from None
    except StorageError:
        raise ServiceError(Kind.UNAVAILABLE, reasons.STORAGE_UNAVAILABLE, "the artifact store is unavailable") from None
    if len(content) != asset.size or hashlib.sha256(content).hexdigest() != asset.sha256:
        raise ServiceError(Kind.UNAVAILABLE, reasons.STORAGE_UNAVAILABLE, "the artifact is unavailable")
    if not current():
        raise _missing()
    return content
