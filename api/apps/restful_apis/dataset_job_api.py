"""Dataset job start, history, status and cancellation routes."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict
from quart import Blueprint, Response, current_app, g
from quart_schema import document_response, validate_request

from api.apps.service_errors import service_error_response
from api.db.services import dataset_job_service
from api.db.services.service_errors import ServiceError
from api.utils.api_utils import json_result
from api.utils.blocking import DB_EXECUTOR, run_blocking

job_bp = Blueprint("dataset_jobs", __name__)
JOBS = "/api/v1/datasets/<dataset_id>/jobs"
JOB = "/api/v1/datasets/<dataset_id>/jobs/<job_id>"
CANCEL = "/api/v1/datasets/<dataset_id>/jobs/<job_id>/cancel"


class StartBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["enrich", "raptor"]


class JobView(BaseModel):
    id: str
    type: str
    run: Literal["1", "2", "3", "4"]
    total: int
    completed: int
    failed: int
    progress: float
    created_at: int
    updated_at: int


class JobEnvelope(BaseModel):
    code: int
    message: str
    data: JobView


class JobList(BaseModel):
    items: list[JobView]


class JobListEnvelope(BaseModel):
    code: int
    message: str
    data: JobList


@job_bp.post(JOBS)
@validate_request(StartBody)
@document_response(JobEnvelope, 200)
async def start(dataset_id: str, data: StartBody) -> Response:
    try:
        settings, principal = current_app.extensions["ragflow_settings"], g.principal
        result = await run_blocking(DB_EXECUTOR, lambda: dataset_job_service.start_job(settings, principal, dataset_id, data.type), timeout=30)
        return json_result(result)
    except ServiceError as exc:
        return service_error_response(exc)


@job_bp.get(JOBS)
@document_response(JobListEnvelope, 200)
async def list_jobs(dataset_id: str) -> Response:
    try:
        result = await run_blocking(DB_EXECUTOR, dataset_job_service.list_jobs, g.principal, dataset_id, timeout=10)
        return json_result(result)
    except ServiceError as exc:
        return service_error_response(exc)


@job_bp.get(JOB)
@document_response(JobEnvelope, 200)
async def get_job(dataset_id: str, job_id: str) -> Response:
    try:
        result = await run_blocking(DB_EXECUTOR, dataset_job_service.get_job, g.principal, dataset_id, job_id, timeout=10)
        return json_result(result)
    except ServiceError as exc:
        return service_error_response(exc)


@job_bp.post(CANCEL)
@document_response(JobEnvelope, 200)
async def cancel(dataset_id: str, job_id: str) -> Response:
    try:
        result = await run_blocking(DB_EXECUTOR, dataset_job_service.cancel_job, g.principal, dataset_id, job_id, timeout=10)
        return json_result(result)
    except ServiceError as exc:
        return service_error_response(exc)
