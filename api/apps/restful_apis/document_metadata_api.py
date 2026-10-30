"""Bounded document metadata edits and authorized dataset metadata views."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr
from quart import Blueprint, Response, current_app, g, request
from quart_schema import document_response, validate_request

from api.apps.service_errors import service_error_response
from api.db.services import document_metadata_service as metadata
from api.db.services.service_errors import ServiceError
from api.utils.api_utils import json_result
from api.utils.blocking import DOCSTORE_EXECUTOR, run_blocking

metadata_bp = Blueprint("document_metadata", __name__)


class MetadataEditBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_ids: list[StrictStr] = Field(min_length=1, max_length=100)
    metadata: dict[str, Any]
    mode: Literal["merge", "replace"] = "merge"


class EditedMetadata(BaseModel):
    document_ids: list[str]
    count: int


class EditedMetadataEnvelope(BaseModel):
    code: int
    message: str
    data: EditedMetadata


class MetadataField(BaseModel):
    name: str
    type: str
    total: int
    values: list[Any]


class FlattenedMetadata(BaseModel):
    fields: list[MetadataField]
    page: int
    page_size: int
    has_more: bool


class FlattenedMetadataEnvelope(BaseModel):
    code: int
    message: str
    data: FlattenedMetadata


class MetadataSchemaField(BaseModel):
    name: str
    type: str
    required: bool


class MetadataConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    enabled: bool
    metadata_schema: list[MetadataSchemaField] = Field(alias="schema")
    model_id: str


class MetadataConfigEnvelope(BaseModel):
    code: int
    message: str
    data: MetadataConfig


@metadata_bp.get("/api/v1/datasets/metadata/flattened")
@document_response(FlattenedMetadataEnvelope, 200)
async def flattened_metadata() -> Response:
    principal = g.principal
    try:
        raw = request.args.get("dataset_ids", "")
        if len(raw) > 1056 or set(request.args) - {"dataset_ids", "page"} or len(request.args.getlist("dataset_ids")) != 1 or len(request.args.getlist("page")) > 1:
            raise metadata._invalid()
        raw_page = request.args.get("page", "1")
        if not raw_page.isdecimal() or len(raw_page) > 3 or not 1 <= int(raw_page) <= 100:
            raise metadata._invalid()
        page = int(raw_page)
        result = await run_blocking(DOCSTORE_EXECUTOR, lambda: metadata.get_flattened_metadata(principal, raw.split(","), page=page), timeout=65)
        return json_result(result)
    except ServiceError as exc:
        return service_error_response(exc)


@metadata_bp.get("/api/v1/datasets/<dataset_id>/metadata/config")
@document_response(MetadataConfigEnvelope, 200)
async def metadata_config(dataset_id: str) -> Response:
    principal = g.principal
    try:
        result = await run_blocking(DOCSTORE_EXECUTOR, lambda: metadata.get_metadata_config(principal, dataset_id), timeout=65)
        return json_result(result)
    except ServiceError as exc:
        return service_error_response(exc)


@metadata_bp.patch("/api/v1/datasets/<dataset_id>/documents/metadatas")
@validate_request(MetadataEditBody)
@document_response(EditedMetadataEnvelope, 200)
async def edit_metadata(dataset_id: str, data: MetadataEditBody) -> Response:
    settings, principal = current_app.extensions["ragflow_settings"], g.principal
    try:
        result = await run_blocking(
            DOCSTORE_EXECUTOR,
            lambda: metadata.batch_edit_metadata(settings, principal, dataset_id, data.document_ids, data.metadata, data.mode),
            timeout=65,
        )
        return json_result(result)
    except ServiceError as exc:
        return service_error_response(exc)
