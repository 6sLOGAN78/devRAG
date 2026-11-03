"""Owned derived-index deletion, alteration history and generated artifact bytes."""
from __future__ import annotations

from pydantic import BaseModel
from quart import Blueprint, Response, current_app, g, request
from quart_schema import document_response

from api.apps.service_errors import service_error_response
from api.db.services import dataset_artifact_service, knowledgebase_service
from api.db.services.service_errors import Kind, ServiceError
from api.utils import reasons
from api.utils.api_utils import json_result
from api.utils.blocking import DB_EXECUTOR, STORAGE_EXECUTOR, run_blocking

artifact_bp = Blueprint("dataset_artifacts", __name__)


class DeleteView(BaseModel):
    type: str
    deleted_count: int
    artifact_count: int


class DeleteEnvelope(BaseModel):
    code: int
    message: str
    data: DeleteView


class AlterationView(BaseModel):
    actor: str
    type: str
    generation: str
    outcome: str
    time: int
    deleted_count: int


class HistoryView(BaseModel):
    items: list[AlterationView]
    total: int
    page: int
    size: int


class HistoryEnvelope(BaseModel):
    code: int
    message: str
    data: HistoryView


@artifact_bp.delete("/api/v1/datasets/<dataset_id>/<index_type>")
@document_response(DeleteEnvelope, 200)
async def delete_derived(dataset_id: str, index_type: str) -> Response:
    try:
        settings, principal = current_app.extensions["ragflow_settings"], g.principal
        result = await run_blocking(DB_EXECUTOR, dataset_artifact_service.delete_derived_index,
                                    settings, principal, dataset_id, index_type, timeout=40)
        return json_result(result)
    except ServiceError as exc:
        return service_error_response(exc)


@artifact_bp.get("/api/v1/datasets/<dataset_id>/artifacts/alteration")
@document_response(HistoryEnvelope, 200)
async def alterations(dataset_id: str) -> Response:
    principal = g.principal
    try:
        await run_blocking(DB_EXECUTOR, knowledgebase_service.load_visible_dataset, principal, dataset_id, timeout=10)
    except ServiceError as exc:
        return service_error_response(exc)
    try:
        if set(request.args) - {"page", "size"}:
            raise ValueError
        page, size = int(request.args.get("page", "1")), int(request.args.get("size", "20"))
    except ValueError:
        return service_error_response(ServiceError(Kind.INVALID, reasons.PARSER_CONFIG_INVALID, "invalid history page"))
    try:
        result = await run_blocking(DB_EXECUTOR, lambda: dataset_artifact_service.list_alterations(
            principal, dataset_id, page=page, size=size), timeout=10)
        return json_result(result)
    except ServiceError as exc:
        return service_error_response(exc)


@artifact_bp.get("/api/v1/documents/artifact/<filename>")
async def download_artifact(filename: str) -> Response:
    try:
        settings, principal = current_app.extensions["ragflow_settings"], g.principal
        data = await run_blocking(STORAGE_EXECUTOR, dataset_artifact_service.read_artifact,
                                  settings, principal, filename, timeout=30)
        return Response(data, mimetype="application/json", headers={
            "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox", "Content-Length": str(len(data)),
            "Content-Disposition": f'attachment; filename="{filename}"',
        })
    except ServiceError as exc:
        return service_error_response(exc)
