"""Generation-bound normalized images owned by a currently visible original document.

Dataset mutation locks serialize persistence/GC with reparse and deletion. Native
inference happens before this module is called; no database checkout spans it.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Sequence

from api.db.database import DB, transaction
from api.db.models import Document, DocumentAsset, PipelineOperationLog, Task
from api.db.services import knowledgebase_service as datasets
from api.db.services.auth_service import Principal
from api.db.services.knowledgebase_service import VisibleDataset
from api.db.services.service_errors import Kind, ServiceError
from api.db.services.task_service import TaskContext
from api.utils import reasons
from common.constants import BUCKET_NAME
from common.settings import Settings
from rag.parsers.assets import MAX_ASSETS, ParsedAsset, asset_object_key
from rag.parsers.errors import FileTooLarge
from rag.svr.control import TaskCancelled, TaskControl
from rag.utils.storage_base import Storage, StorageError, StorageNotFound
from rag.utils.storage_factory import get_storage

_ID = re.compile(r"[0-9a-f]{32}")


def _missing() -> ServiceError:
    return ServiceError(Kind.NOT_FOUND, reasons.DATASET_NOT_FOUND, "not found")


def _latest(doc_id: str) -> PipelineOperationLog | None:
    return PipelineOperationLog.select().where(PipelineOperationLog.document_id == doc_id).order_by(PipelineOperationLog.create_time.desc(), PipelineOperationLog.id).first()


def current_generation(ctx: TaskContext) -> str | None:
    with DB.connection_context():
        doc = Document.get_or_none((Document.id == ctx.doc_id) & (Document.kb_id == ctx.dataset_id))
        task = Task.get_or_none((Task.id == ctx.task_id) & (Task.doc_id == ctx.doc_id))
        log = _latest(ctx.doc_id)
        if doc is None or doc.run != "1" or task is None:
            raise TaskCancelled("task replaced")
        return log.id if log and log.operation_status == "running" else None


def persist_assets(settings: Settings, ctx: TaskContext, generation_id: str | None, assets: Sequence[ParsedAsset], control: TaskControl, *, storage: Storage | None = None) -> list[str]:
    unique = {(a.kind, a.sha256): a for a in assets}
    if len(unique) > MAX_ASSETS or sum(len(a.content) for a in unique.values()) > 24 * 1024 * 1024:
        raise FileTooLarge()
    if not unique:
        return []
    blobs = storage if storage is not None else get_storage(settings)
    ids = []
    with datasets._named_lock(datasets.upload_lock_name(ctx.dataset_id), 10, "another dataset change is running"):
        control.check()
        if generation_id is None or current_generation(ctx) != generation_id:
            raise TaskCancelled("task replaced")
        for asset in unique.values():
            control.check()
            key = asset_object_key(ctx.tenant_id, ctx.doc_id, asset.kind, asset.sha256)
            with DB.connection_context():
                previous = DocumentAsset.get_or_none(
                    (DocumentAsset.tenant_id == ctx.tenant_id) & (DocumentAsset.doc_id == ctx.doc_id) & (DocumentAsset.kind == asset.kind) & (DocumentAsset.sha256 == asset.sha256)
                )
            # The mutation lock prevents a concurrent delete/reparse/GC from removing this key.
            try:
                blobs.put(BUCKET_NAME, key, asset.content)
                control.check()
                if current_generation(ctx) != generation_id:
                    raise TaskCancelled("task replaced")
                with DB.connection_context(), transaction():
                    # Cancel does not take the dataset lock; check the document under its row lock too.
                    doc = Document.select().where(Document.id == ctx.doc_id).for_update().first()
                    if doc is None or doc.run != "1":
                        raise TaskCancelled("document cancelled")
                    values = dict(
                        tenant_id=ctx.tenant_id,
                        kb_id=ctx.dataset_id,
                        doc_id=ctx.doc_id,
                        kind=asset.kind,
                        object_key=key,
                        mime_type="image/png",
                        size=len(asset.content),
                        sha256=asset.sha256,
                        generation_id=generation_id,
                        caption=asset.caption,
                        page=asset.page,
                        width=asset.width,
                        height=asset.height,
                    )
                    identifier = previous.id if previous else uuid.uuid4().hex
                    if previous:
                        DocumentAsset.update(**values).where(DocumentAsset.id == identifier).execute()
                    else:
                        DocumentAsset.create(id=identifier, **values)
                    ids.append(identifier)
            except BaseException:
                if previous is None:
                    from api.db.services.file_service import release_blobs

                    release_blobs(blobs, [key], "asset")
                raise
    return ids


def _published(visible: VisibleDataset, doc_id: str) -> str:
    doc = Document.get_or_none((Document.id == doc_id) & (Document.kb_id == visible.dataset.id))
    log = _latest(doc_id)
    if doc is None or not doc.location or doc.run != "3" or log is None or log.operation_status != "done":
        raise _missing()
    return log.id


def list_assets(visible: VisibleDataset, doc_id: str) -> list[dict]:
    with DB.connection_context():
        try:
            generation = _published(visible, doc_id)
        except ServiceError:
            return []
        rows = (
            DocumentAsset.select()
            .where((DocumentAsset.tenant_id == visible.scope.tenant_id) & (DocumentAsset.kb_id == visible.dataset.id) & (DocumentAsset.doc_id == doc_id) & (DocumentAsset.generation_id == generation))
            .order_by(DocumentAsset.page, DocumentAsset.id)
            .limit(MAX_ASSETS)
        )
        return [dict(id=a.id, kind=a.kind, caption=a.caption, page=a.page, width=a.width, height=a.height) for a in rows]


def read_asset(settings: Settings, principal: Principal, image_id: str, *, storage: Storage | None = None) -> bytes:
    if not isinstance(image_id, str) or _ID.fullmatch(image_id) is None:
        raise _missing()
    with DB.connection_context():
        asset = DocumentAsset.get_or_none(DocumentAsset.id == image_id)
    if asset is None or asset.kind not in {"image", "table"} or not asset.doc_id:
        raise _missing()
    visible = datasets.load_visible_dataset(principal, asset.kb_id)
    with DB.connection_context():
        generation = _published(visible, asset.doc_id)
    if asset.tenant_id != visible.scope.tenant_id or asset.generation_id != generation:
        raise _missing()
    blobs = storage if storage is not None else get_storage(settings)
    try:
        # All size/digest metadata was produced by the bounded normalized-image contract.
        if blobs.size(BUCKET_NAME, asset.object_key) != asset.size:
            raise _missing()
        data = blobs.get(BUCKET_NAME, asset.object_key)
    except StorageNotFound:
        raise _missing() from None
    except StorageError:
        raise ServiceError(Kind.UNAVAILABLE, reasons.STORAGE_UNAVAILABLE, "the file store is not available") from None
    if len(data) != asset.size or hashlib.sha256(data).hexdigest() != asset.sha256:
        raise ServiceError(Kind.UNAVAILABLE, reasons.STORAGE_UNAVAILABLE, "the image is not available")
    # Revalidate after I/O so a concurrent deletion or reparse cannot publish stale bytes.
    visible = datasets.load_visible_dataset(principal, asset.kb_id)
    with DB.connection_context():
        if _published(visible, asset.doc_id) != generation or not DocumentAsset.select().where(DocumentAsset.id == asset.id).exists():
            raise _missing()
    return data


def release_rows(doc_ids: Sequence[str]) -> list[str]:
    """Called in the document deletion transaction, after its authorization/row locks."""
    keys = [a.object_key for a in DocumentAsset.select(DocumentAsset.object_key).where(DocumentAsset.doc_id.in_(doc_ids))]
    DocumentAsset.delete().where(DocumentAsset.doc_id.in_(doc_ids)).execute()
    return keys


def prune_obsolete(settings: Settings, dataset_id: str, doc_id: str, *, storage: Storage | None = None) -> None:
    blobs = storage if storage is not None else get_storage(settings)
    with datasets._named_lock(datasets.upload_lock_name(dataset_id), 10, "another dataset change is running"):
        with DB.connection_context(), transaction():
            doc = Document.select().where((Document.id == doc_id) & (Document.kb_id == dataset_id)).for_update().first()
            log = _latest(doc_id)
            if doc is None or doc.run != "3" or log is None or log.operation_status != "done":
                return
            obsolete = list(DocumentAsset.select().where((DocumentAsset.doc_id == doc_id) & (DocumentAsset.generation_id != log.id)))
            if obsolete:
                DocumentAsset.delete().where(DocumentAsset.id.in_([a.id for a in obsolete])).execute()
        from api.db.services.file_service import release_blobs

        release_blobs(blobs, [asset.object_key for asset in obsolete], "asset reparse")
