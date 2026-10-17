"""Ingestion read routes: summary, parsing log, one log entry, the embedding-model check and task status (plan 04-19; KB-14..16, KB-19, DOC-22, DOC-23, D-07, D-08, D-23).

* ``GET  /api/v1/datasets/<dataset_id>/ingestions/summary`` answers ``unstart running done failed cancelled partial chunk_total token_total``.
* ``GET  /api/v1/datasets/<dataset_id>/ingestions?page=&size=`` lists parsing runs, newest first (``size`` 1 to 100, default 20). The outcome key is ``result``.
* ``GET  /api/v1/datasets/<dataset_id>/ingestions/<log_id>`` answers one run with its progress lines (at most 3000, redacted).
* ``POST /api/v1/datasets/<dataset_id>/embedding/check`` with ``{"embd_id"?: "..."}`` embeds one fixed probe and answers ``{ok, dimension, expected}``.
  It needs the dataset manage rule and is counted per workspace against the same window as chunk writes, because it costs a provider call.
* ``GET  /v1/task/status/<task_id>`` answers one task; the task's dataset must be visible to the caller.

Reads need only dataset visibility. An absent, foreign or invisible dataset, run or task is the one 404. Errors carry a step, a code and a fixed plain
sentence; nothing the worker stored as free text reaches a client. This module imports no models and no database library.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict
from quart import Blueprint, Response, current_app, g, request
from quart_schema import document_response, validate_request

from api.apps.service_errors import service_error_response
from api.db.services import ingestion_read_service as reads
from api.db.services import ingestion_service
from api.db.services.service_errors import Kind, ServiceError
from api.utils import reasons
from api.utils.api_utils import json_result
from api.utils.blocking import DB_EXECUTOR, PROVIDER_EXECUTOR, run_blocking
from common.settings import Settings

ingestion_bp = Blueprint("ingestion", __name__)

# Identical to the endpoint rows in conf/routes.yaml (Quart spells a path parameter <name>, the registry {name}).
SUMMARY = "/api/v1/datasets/<dataset_id>/ingestions/summary"
LOGS = "/api/v1/datasets/<dataset_id>/ingestions"
LOG = "/api/v1/datasets/<dataset_id>/ingestions/<log_id>"
CHECK = "/api/v1/datasets/<dataset_id>/embedding/check"
TASK = "/v1/task/status/<task_id>"

DB_TIMEOUT_SECONDS = 10.0
CHECK_TIMEOUT_SECONDS = 45.0  # the embedding driver gives up after 30 s; the typed error wins over this deadline
_WHOLE_NUMBER = re.compile(r"[0-9]{1,9}")


class SummaryView(BaseModel):
    unstart: int
    running: int
    done: int
    failed: int
    cancelled: int
    partial: int
    chunk_total: int
    token_total: int


class ErrorView(BaseModel):
    step: str
    code: str
    message: str
    detail: str | None = None


class LogView(BaseModel):
    id: str
    document_id: str
    document_name: str
    started_at: int
    duration_seconds: float
    result: str
    attempts: int
    max_attempts: int
    retried: bool
    chunk_count: int
    pages_total: int | None
    pages_without_text: int | None
    error: ErrorView | None


class LogDetailView(LogView):
    log: list[str]


class LogPage(BaseModel):
    items: list[LogView]
    total: int


class TaskView(BaseModel):
    id: str
    doc_id: str
    dataset_id: str
    from_page: int
    to_page: int
    progress: float
    progress_message: str
    attempts: int
    finished: bool
    failed: bool
    error: ErrorView | None


class CheckView(BaseModel):
    ok: bool
    dimension: int
    expected: int


class SummaryEnvelope(BaseModel):
    code: int
    message: str
    data: SummaryView


class LogPageEnvelope(BaseModel):
    code: int
    message: str
    data: LogPage


class LogDetailEnvelope(BaseModel):
    code: int
    message: str
    data: LogDetailView


class TaskEnvelope(BaseModel):
    code: int
    message: str
    data: TaskView


class CheckEnvelope(BaseModel):
    code: int
    message: str
    data: CheckView


class EmbeddingCheckBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    embd_id: str | None = None


def _settings() -> Settings:
    return current_app.extensions["ragflow_settings"]


def _whole(name: str, default: int, low: int, high: int) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    if _WHOLE_NUMBER.fullmatch(raw) is None or not low <= int(raw) <= high:
        raise ServiceError(Kind.INVALID, reasons.QUERY_INVALID, f"{name} must be a whole number from {low} to {high}")
    return int(raw)


@document_response(SummaryEnvelope, 200)
async def ingestion_summary(dataset_id: str) -> Response:
    try:
        principal = g.principal  # read on the loop: the request context does not follow the call into the worker thread

        def read() -> dict[str, int]:
            return reads.ingestion_summary(reads.authorize_read(principal, dataset_id))

        return json_result(await run_blocking(DB_EXECUTOR, read, timeout=DB_TIMEOUT_SECONDS))
    except ServiceError as exc:
        return service_error_response(exc)


@document_response(LogPageEnvelope, 200)
async def list_logs(dataset_id: str) -> Response:
    try:
        settings = _settings()
        page = _whole("page", 1, 1, reads.MAX_PAGE)
        size = _whole("size", reads.DEFAULT_PAGE_SIZE, 1, reads.MAX_PAGE_SIZE)
        principal = g.principal

        def read() -> dict:
            return reads.list_logs(reads.authorize_read(principal, dataset_id), page, size, settings=settings)

        return json_result(await run_blocking(DB_EXECUTOR, read, timeout=DB_TIMEOUT_SECONDS))
    except ServiceError as exc:
        return service_error_response(exc)


@document_response(LogDetailEnvelope, 200)
async def get_log(dataset_id: str, log_id: str) -> Response:
    try:
        settings = _settings()
        principal = g.principal

        def read() -> dict:
            return reads.get_log(reads.authorize_read(principal, dataset_id), log_id, settings=settings)

        return json_result(await run_blocking(DB_EXECUTOR, read, timeout=DB_TIMEOUT_SECONDS))
    except ServiceError as exc:
        return service_error_response(exc)


@validate_request(EmbeddingCheckBody)
@document_response(CheckEnvelope, 200)
async def embedding_check(dataset_id: str, data: EmbeddingCheckBody) -> Response:
    try:
        settings = _settings()
        principal = g.principal
        embd_id = data.embd_id
        visible = await run_blocking(DB_EXECUTOR, reads.authorize_check, principal, dataset_id, timeout=DB_TIMEOUT_SECONDS)
        await run_blocking(DB_EXECUTOR, ingestion_service.write_rate_guard, settings, visible.scope.tenant_id, timeout=DB_TIMEOUT_SECONDS)
        result = await run_blocking(
            PROVIDER_EXECUTOR,
            lambda: reads.embedding_check(settings, visible, principal, embd_id),
            timeout=CHECK_TIMEOUT_SECONDS,
        )
        return json_result(result)
    except ServiceError as exc:
        return service_error_response(exc)


@document_response(TaskEnvelope, 200)
async def task_status(task_id: str) -> Response:
    try:
        principal = g.principal
        return json_result(await run_blocking(DB_EXECUTOR, reads.task_status, principal, task_id, timeout=DB_TIMEOUT_SECONDS))
    except ServiceError as exc:
        return service_error_response(exc)


ingestion_bp.add_url_rule(SUMMARY, endpoint="ingestion_summary", view_func=ingestion_summary, methods=["GET"])
ingestion_bp.add_url_rule(LOGS, endpoint="list_logs", view_func=list_logs, methods=["GET"])
ingestion_bp.add_url_rule(LOG, endpoint="get_log", view_func=get_log, methods=["GET"])
ingestion_bp.add_url_rule(CHECK, endpoint="embedding_check", view_func=embedding_check, methods=["POST"])
ingestion_bp.add_url_rule(TASK, endpoint="task_status", view_func=task_status, methods=["GET"])
