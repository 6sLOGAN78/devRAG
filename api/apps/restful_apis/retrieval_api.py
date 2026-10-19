"""Retrieval test route (plan 05-04; RETR-16..18, RETR-23, KB-18, TEN-03, E2E-07, D-19, D-20, R-194, R-205).

``POST /api/v1/datasets/search`` with ``{"dataset_ids": [...], "question": "...", "doc_ids"?, "similarity_threshold"?, "vector_similarity_weight"?,
"top_k"?, "fusion"?, "rerank_id"?, "page"?, "size"?, "tenant_id"?}`` answers ``{"total", "chunks", "doc_aggs", "rerank_applied", "timings"}``.

The call acts in one workspace (``tenant_id`` or the caller's own). A dataset id the caller cannot open, that belongs to another workspace or that
does not exist is the one 404 for the whole request and no search runs. Numeric bounds are the service's check so the reason reaches the client.
A call spends one embedding request and is counted per workspace and user (429 with ``Retry-After``). The question text is never logged.
Settings and the principal are read on the loop; the blocking work runs in the bounded provider pool with a deadline above the driver's own 30 s.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from quart import Blueprint, Response, current_app, g
from quart_schema import document_response, validate_request

from api.apps.handler_support import acting_scope, forbid_unless
from api.apps.service_errors import not_found_response, service_error_response
from api.db.services import retrieval_service
from api.db.services.service_errors import ServiceError
from api.utils.api_utils import json_result
from api.utils.blocking import PROVIDER_EXECUTOR, run_blocking
from common.settings import Settings

retrieval_bp = Blueprint("retrieval", __name__)

# Identical to the endpoint row in conf/routes.yaml.
SEARCH = "/api/v1/datasets/search"

AREA = "datasets"
RETRIEVAL_TEST = "retrieval_test"
GUARD_TIMEOUT_SECONDS = 10.0
SEARCH_TIMEOUT_SECONDS = 45.0  # the embedding driver gives up after 30 s; the typed error wins over this deadline
_TENANT_ID_PATTERN = r"^[0-9a-f]{32}$"


class SearchBody(BaseModel):
    """Only these fields exist. Ranges and id shapes are checked in the service so the reason reaches the client."""

    model_config = ConfigDict(extra="forbid")

    dataset_ids: list[str]
    question: str
    doc_ids: list[str] | None = None
    similarity_threshold: float = 0.2
    vector_similarity_weight: float = 0.3
    top_k: int | None = None
    fusion: str = "weighted_sum"
    rerank_id: str | None = None
    page: int = 1
    size: int = 10
    tenant_id: str | None = Field(default=None, pattern=_TENANT_ID_PATTERN)


class SearchResult(BaseModel):
    total: int
    chunks: list[dict[str, Any]]
    doc_aggs: list[dict[str, Any]]
    rerank_applied: bool
    timings: dict[str, float | None]


class SearchEnvelope(BaseModel):
    code: int
    message: str
    data: SearchResult


def _settings() -> Settings:
    return current_app.extensions["ragflow_settings"]


@validate_request(SearchBody)
@document_response(SearchEnvelope, 200)
async def search_datasets(data: SearchBody) -> Response:
    try:
        scope = await acting_scope(data.tenant_id)
        if scope is None:
            return not_found_response()
        denied = forbid_unless(scope, AREA, RETRIEVAL_TEST)
        if denied is not None:
            return denied
        settings = _settings()  # read here, on the loop: the request context does not follow the call into the worker thread
        principal = g.principal
        body = data.model_dump(exclude={"tenant_id"})
        await run_blocking(
            PROVIDER_EXECUTOR, retrieval_service.retrieval_rate_guard, settings, scope.tenant_id, principal.user_id, timeout=GUARD_TIMEOUT_SECONDS
        )
        view = await run_blocking(
            PROVIDER_EXECUTOR,
            lambda: retrieval_service.search(principal, scope, body, settings),
            timeout=SEARCH_TIMEOUT_SECONDS,
        )
        return json_result(view)
    except ServiceError as exc:
        return service_error_response(exc)


retrieval_bp.add_url_rule(SEARCH, endpoint="search_datasets", view_func=search_datasets, methods=["POST"])
