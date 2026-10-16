"""Parse route: start, cancel and re-parse documents (plan 04-14; DOC-09..11, ING-12, KB-19, E2E-05, D-01..D-04, D-06, D-09, D-13, D-15, D-19).

``POST /api/v1/datasets/<dataset_id>/documents/parse`` with ``{"doc_ids": [...], "run": "1" | "2", "confirm_replace": false}``.

* ``run "1"`` starts (or restarts) parsing and answers ``{"started": [{"id", "tasks"}]}``. A re-parse that would replace chunks is 409
  ``confirm_required`` with per-document counts unless ``confirm_replace`` is true.
* ``run "2"`` cancels the running documents among the ids and answers ``{"cancelled": [ids]}``; chunks already indexed stay.

The request is all or nothing; the service owns the order of the checks and the refusal reasons. An absent, foreign or private-to-others dataset is
the one 404. Parse requests per workspace are counted against ``parse_rate_max`` per ``parse_rate_window_seconds`` (429 with ``Retry-After``).
The body names only these three fields. Settings and the principal are read on the loop; the blocking work runs in bounded executors.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict
from quart import Blueprint, Response, current_app, g
from quart_schema import document_response, validate_request

from api.apps.service_errors import service_error_response
from api.db.services import ingestion_service
from api.db.services.service_errors import ServiceError
from api.utils.api_utils import json_result
from api.utils.blocking import DB_EXECUTOR, DOCSTORE_EXECUTOR, run_blocking
from common.settings import Settings

parse_bp = Blueprint("parse", __name__)

# Identical to the endpoint row in conf/routes.yaml (Quart spells a path parameter <name>, the registry {name}).
PARSE = "/api/v1/datasets/<dataset_id>/documents/parse"

AUTHORIZE_TIMEOUT_SECONDS = 10.0
# The service waits up to 30 s for the dataset lock and the index engine has its own deadline; the handler waits longer so the typed errors win.
PARSE_TIMEOUT_SECONDS = 60.0


class ParseBody(BaseModel):
    """Only these fields exist. The count and shape of the ids are the service's check, so a bad one is a typed ``ids_invalid``."""

    model_config = ConfigDict(extra="forbid")

    doc_ids: list[str]
    run: Literal["1", "2"]
    confirm_replace: bool = False


class StartedDocument(BaseModel):
    id: str
    tasks: int


class ParseResult(BaseModel):
    started: list[StartedDocument] | None = None
    cancelled: list[str] | None = None


class ParseEnvelope(BaseModel):
    code: int
    message: str
    data: ParseResult


def _settings() -> Settings:
    return current_app.extensions["ragflow_settings"]


@validate_request(ParseBody)
@document_response(ParseEnvelope, 200)
async def parse_documents(dataset_id: str, data: ParseBody) -> Response:
    try:
        settings = _settings()  # read here, on the loop
        principal = g.principal
        ids = list(data.doc_ids)
        confirm = data.confirm_replace
        visible = await run_blocking(DB_EXECUTOR, ingestion_service.authorize_parse, principal, dataset_id, timeout=AUTHORIZE_TIMEOUT_SECONDS)
        if data.run == "2":
            cancelled = await run_blocking(
                DOCSTORE_EXECUTOR,
                lambda: ingestion_service.cancel_parse(settings, visible, principal, ids),
                timeout=PARSE_TIMEOUT_SECONDS,
            )
            return json_result({"cancelled": cancelled})
        await run_blocking(DB_EXECUTOR, ingestion_service.parse_rate_guard, settings, visible.scope.tenant_id, timeout=AUTHORIZE_TIMEOUT_SECONDS)
        started = await run_blocking(
            DOCSTORE_EXECUTOR,
            lambda: ingestion_service.start_parse(settings, visible, principal, ids, confirm),
            timeout=PARSE_TIMEOUT_SECONDS,
        )
        return json_result({"started": [{"id": s.doc_id, "tasks": s.task_count} for s in started]})
    except ServiceError as exc:
        return service_error_response(exc)


parse_bp.add_url_rule(PARSE, endpoint="parse_documents", view_func=parse_documents, methods=["POST"])
