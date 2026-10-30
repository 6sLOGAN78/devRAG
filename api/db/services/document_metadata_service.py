"""Validation and deterministic summaries for user-controlled document metadata."""
from __future__ import annotations

import json
import math
import re
import time
import unicodedata
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from api.db.database import DB
from api.db.models import Document
from api.db.models.base import current_timestamp_ms, timestamp_to_date
from api.db.services.auth_service import Principal
from api.db.services.document_service import authorize_upload
from api.db.services.knowledgebase_service import load_visible_dataset, _named_lock, upload_lock_name
from api.db.services.parser_config import ParserConfig
from api.db.services.service_errors import Kind, ServiceError
from api.utils import reasons
from common.doc_store.doc_store_base import DocStoreError, OrderByExpr, index_name
from common.settings import Settings
from rag.utils.es_conn import get_doc_store

MAX_FIELDS = 32
MAX_BYTES = 16 * 1024
MAX_ARRAY = 32
MAX_STRING = 4096
MAX_VALUES_PER_FIELD = 10000
VALUE_PAGE_SIZE = 100
MAX_DOCUMENTS = 100
MAX_INDEX_ROWS = 10000
MAX_AGGREGATE_BYTES = 8 * 1024 * 1024
MAX_DATASETS = 32
DEADLINE_SECONDS = 30
INDEX_FIELD = "meta_fields_list"  # Existing mapping stores *_list as unindexed source text.
_ID = re.compile(r"[0-9a-f]{32}\Z")
_KEY = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
_RESERVED = frozenset({"provenance", "source", "generation", "generated", "internal"})


def _key(value: object) -> str:
    if not isinstance(value, str) or not _KEY.fullmatch(value):
        raise ValueError("invalid metadata key")
    key = value.casefold()
    if key in _RESERVED or key.startswith("internal_") or key.startswith("generated_"):
        raise ValueError("reserved metadata key")
    return key


def _scalar(value: object) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, bool)):
        if isinstance(value, str) and (len(value) > MAX_STRING or any(unicodedata.category(c) == "Cc" and c not in "\t\n" for c in value)):
            raise ValueError("invalid metadata text")
        return value
    if isinstance(value, (int, float)):
        try:
            if math.isfinite(value) and len(str(value)) <= 64:
                return value
        except (OverflowError, ValueError):
            pass
    raise ValueError("invalid metadata value")


def validate_metadata(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping) or len(value) > MAX_FIELDS:
        raise ValueError("invalid metadata fields")
    normalized: dict[str, Any] = {}
    for raw_key, raw_value in value.items():
        key = _key(raw_key)
        if key in normalized:
            raise ValueError("duplicate metadata key")
        if isinstance(raw_value, list):
            if len(raw_value) > MAX_ARRAY:
                raise ValueError("metadata array too large")
            items = [_scalar(item) for item in raw_value]
            if any(not isinstance(item, str) for item in items):
                raise ValueError("metadata arrays must contain text")
            normalized[key] = items
        else:
            normalized[key] = _scalar(raw_value)
    if len(json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode()) > MAX_BYTES:
        raise ValueError("metadata too large")
    return dict(sorted(normalized.items()))


def merge_metadata(old: object, incoming: object, *, mode: str) -> dict[str, Any]:
    if mode not in {"merge", "replace"}:
        raise ValueError("invalid metadata mode")
    current = validate_metadata(old)
    change = validate_metadata(incoming)
    return validate_metadata({**current, **change} if mode == "merge" else change)


def flatten_metadata(rows: list[object], *, page: int = 1) -> list[dict[str, Any]]:
    if type(page) is not int or not 1 <= page <= 100:
        raise ValueError("invalid metadata page")
    if len(rows) > 10000:
        raise ValueError("too many metadata rows")
    values: dict[str, dict[str, Any]] = {}
    types: dict[str, str] = {}
    for row in rows:
        for name, value in validate_metadata(row).items():
            kind = "string_array" if isinstance(value, list) else "null" if value is None else "boolean" if isinstance(value, bool) else "number" if isinstance(value, (int, float)) else "string"
            types[name] = kind if name not in types or types[name] == kind else "mixed"
            encoded = json.dumps(value, sort_keys=True, ensure_ascii=False)
            bucket = values.setdefault(name, {})
            bucket[encoded] = value
            if len(bucket) > MAX_VALUES_PER_FIELD:
                raise ValueError("too many metadata values")
            if len(values) > MAX_FIELDS:
                raise ValueError("too many metadata fields")
    start = (page - 1) * VALUE_PAGE_SIZE
    def ordered_keys(name: str) -> list[str]:
        kind = types[name]
        if kind in {"number", "boolean", "string"}:
            return sorted(values[name], key=lambda key: (values[name][key], key))
        if kind == "string_array":
            return sorted(values[name], key=lambda key: (tuple(values[name][key]), key))
        return sorted(values[name])
    return [{"name": name, "type": types[name], "total": len(values[name]), "values": [values[name][key] for key in ordered_keys(name)[start:start + VALUE_PAGE_SIZE]]} for name in sorted(values)]


def _invalid(message: str = "the metadata selection is not valid") -> ServiceError:
    return ServiceError(Kind.INVALID, reasons.FIELDS_INVALID, message)


def _unavailable() -> ServiceError:
    return ServiceError(Kind.UNAVAILABLE, reasons.INDEX_UNAVAILABLE, "the search index is not available, try again shortly")


def _ids(raw: object, limit: int) -> list[str]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= limit or any(not isinstance(v, str) or _ID.fullmatch(v) is None for v in raw) or len(set(raw)) != len(raw):
        raise _invalid()
    return raw


def _current_user_fields(stored: object) -> dict[str, Any]:
    if not isinstance(stored, dict):
        raise _invalid("stored metadata is invalid")
    if any(not isinstance(key, str) for key in stored):
        raise _invalid("stored metadata is invalid")
    return validate_metadata({key: value for key, value in stored.items() if not key.startswith("_")})


def _merged_stored(stored: object, incoming: dict[str, Any], mode: str) -> dict[str, Any]:
    current = _current_user_fields(stored)
    internal = {key: value for key, value in stored.items() if key.startswith("_")}
    if set(internal) - {"_generated", "_provenance"}:
        raise _invalid("stored metadata is invalid")
    if "_generated" in internal:
        internal["_generated"] = validate_metadata(internal["_generated"])
    if "_provenance" in internal:
        raw = internal["_provenance"]
        if not isinstance(raw, dict) or len(raw) > MAX_FIELDS or any(not isinstance(key, str) or not _KEY.fullmatch(key) or not isinstance(value, str) or len(value) > 128 for key, value in raw.items()):
            raise _invalid("stored metadata is invalid")
    result = {**merge_metadata(current, incoming, mode=mode), **internal}
    if len(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()) > MAX_BYTES:
        raise ValueError("metadata too large")
    return result


def _deadline(started: float) -> None:
    if time.monotonic() - started > DEADLINE_SECONDS:
        raise ServiceError(Kind.UNAVAILABLE, reasons.BUSY, "the metadata operation took too long, try again shortly")


def _index_rows(engine: Any, tenant_id: str, dataset_id: str, doc_ids: list[str], started: float) -> list[dict[str, Any]]:
    condition = {"doc_id": doc_ids, "must_not": {"removed_kwd": "Y"}}
    name = index_name(tenant_id)
    total = engine.search([], [], condition, [], None, 0, 0, name, [dataset_id]).total
    if total > MAX_INDEX_ROWS:
        raise ServiceError(Kind.CONFLICT, reasons.FIELDS_INVALID, "too many indexed chunks for this metadata operation")
    rows: list[dict[str, Any]] = []
    for offset in range(0, total, 500):
        _deadline(started)
        result = engine.search(["id", "doc_id", "task_id"], [], condition, [], OrderByExpr().asc("id"), offset, 500, name, [dataset_id])
        if result.total != total or len(rows) + len(result.hits) > MAX_INDEX_ROWS:
            raise _unavailable()
        rows.extend(result.hits)
    return rows


def batch_edit_metadata(
    settings: Settings,
    principal: Principal,
    dataset_id: str,
    document_ids: object,
    metadata: object,
    mode: str,
    *,
    doc_store: Any = None,
) -> dict[str, Any]:
    ids = _ids(document_ids, MAX_DOCUMENTS)
    if mode not in {"merge", "replace"}:
        raise _invalid()
    try:
        incoming = validate_metadata(metadata)
    except ValueError:
        raise _invalid("the metadata fields are not valid") from None
    authorize_upload(principal, dataset_id)
    started = time.monotonic()
    with _named_lock(upload_lock_name(dataset_id), 10, "another change to this dataset is running, try again shortly"):
        visible = authorize_upload(principal, dataset_id)
        with DB.connection_context():
            documents = list(Document.select(Document.id, Document.kb_id, Document.run, Document.meta_fields).where((Document.kb_id == dataset_id) & Document.id.in_(ids)))
        if len(documents) != len(ids):
            raise ServiceError(Kind.NOT_FOUND, reasons.DATASET_NOT_FOUND, "not found")
        if any(document.run == "1" for document in documents):
            raise ServiceError(Kind.CONFLICT, reasons.PARSE_RUNNING, "wait for parsing to finish before editing metadata")
        changed = {}
        try:
            for document in documents:
                changed[document.id] = _merged_stored(document.meta_fields or {}, incoming, mode)
        except ValueError:
            raise _invalid("stored metadata is invalid") from None
        engine = doc_store if doc_store is not None else get_doc_store(settings)
        try:
            rows = _index_rows(engine, visible.scope.tenant_id, dataset_id, ids, started)
            for row in rows:
                _deadline(started)
                doc_id = row.get("doc_id")
                if doc_id not in changed or not isinstance(row.get("id"), str):
                    raise _unavailable()
                encoded = json.dumps(changed[doc_id], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                condition = {"id": [row["id"]], "doc_id": [doc_id], "task_id": [row.get("task_id", "")]}
                if not engine.update(condition, {INDEX_FIELD: encoded}, index_name(visible.scope.tenant_id), dataset_id):
                    raise _unavailable()
        except (DocStoreError, TypeError, ValueError, KeyError):
            raise _unavailable() from None
        _deadline(started)
        with DB.connection_context(), DB.atomic():
            current = list(Document.select(Document.id, Document.run).where((Document.kb_id == dataset_id) & Document.id.in_(ids)))
            if len(current) != len(ids):
                raise ServiceError(Kind.NOT_FOUND, reasons.DATASET_NOT_FOUND, "not found")
            if any(doc.run == "1" for doc in current):
                raise ServiceError(Kind.CONFLICT, reasons.PARSE_RUNNING, "a selected document changed while metadata was saved")
            stamp = current_timestamp_ms()
            for doc_id in ids:
                if Document.update(meta_fields=changed[doc_id], update_time=stamp, update_date=timestamp_to_date(stamp)).where((Document.id == doc_id) & (Document.kb_id == dataset_id)).execute() != 1:
                    raise ServiceError(Kind.CONFLICT, reasons.FIELDS_INVALID, "a selected document changed while metadata was saved")
    load_visible_dataset(principal, dataset_id)
    return {"document_ids": ids, "count": len(ids)}


def get_flattened_metadata(principal: Principal, dataset_ids: object, *, page: int = 1) -> dict[str, Any]:
    if type(page) is not int or not 1 <= page <= 100:
        raise _invalid()
    ids = _ids(dataset_ids, MAX_DATASETS)
    visible = [load_visible_dataset(principal, dataset_id) for dataset_id in ids]
    rows = []
    bytes_seen = 0
    started = time.monotonic()
    with DB.connection_context():
        for dataset in visible:
            query = Document.select(Document.meta_fields).where(Document.kb_id == dataset.dataset.id).limit(MAX_INDEX_ROWS - len(rows) + 1)
            try:
                for row in query.iterator():
                    if len(rows) >= MAX_INDEX_ROWS:
                        raise ServiceError(Kind.CONFLICT, reasons.FIELDS_INVALID, "too many documents for this metadata view")
                    if len(rows) % 64 == 0:
                        _deadline(started)
                    fields = _current_user_fields(row.meta_fields or {})
                    bytes_seen += len(json.dumps(fields, ensure_ascii=False, separators=(",", ":")).encode())
                    if bytes_seen > MAX_AGGREGATE_BYTES:
                        raise ServiceError(Kind.CONFLICT, reasons.FIELDS_INVALID, "too much metadata for this view")
                    rows.append(fields)
            except (ValueError, TypeError, AttributeError):
                raise _invalid("stored metadata is invalid") from None
    try:
        fields = flatten_metadata(rows, page=page)
    except ValueError:
        raise _invalid("stored metadata is invalid") from None
    for dataset_id in ids:
        load_visible_dataset(principal, dataset_id)
    return {"fields": fields, "page": page, "page_size": VALUE_PAGE_SIZE, "has_more": any(field["total"] > page * VALUE_PAGE_SIZE for field in fields)}


def get_metadata_config(principal: Principal, dataset_id: str) -> dict[str, Any]:
    visible = load_visible_dataset(principal, dataset_id)
    try:
        config = ParserConfig.model_validate(visible.dataset.parser_config)
    except ValidationError:
        raise _invalid("stored metadata configuration is invalid") from None
    return {
        "enabled": config.auto_metadata,
        "schema": [field.model_dump() for field in config.metadata_schema],
        "model_id": config.metadata_model_id,
    }
