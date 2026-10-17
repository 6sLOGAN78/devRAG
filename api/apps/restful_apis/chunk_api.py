"""Chunk routes: list, add, edit and switch the chunks of one document (plan 04-18; CHUNK-16, CHUNK-18..21, IDX-07, KB-19, BE-06, D-10..D-12, D-26).

* ``GET  /api/v1/datasets/<dataset_id>/documents/<doc_id>/chunks?page=&size=&keywords=&available=`` answers ``{"items", "total", "page_sizes"}``;
  ``size`` is 1 to 100 (default 20), ``available`` is ``0`` or ``1``. Reads need only dataset visibility.
* ``POST  .../chunks`` with ``{"content_with_weight": "..."}`` adds a hand-made chunk and answers it.
* ``PATCH .../chunks/<chunk_id>`` with ``{"content_with_weight"?: "...", "available"?: bool}`` edits the text and/or the chunk's own switch and answers it.

Request names follow ``docs/04-api`` (``content_with_weight``); responses say ``text`` (UI-SPEC planner note 8). Bodies refuse unknown fields.
A write embeds first and writes only on success (D-11), so it runs in the bounded provider pool with a 45 s deadline above the driver's own 30 s.
An add or text edit is counted per workspace against the parse window (``chunk:{tenant}``). An absent, foreign or private-to-others dataset, a
document of another dataset and a chunk that is not this document's are all the one 404.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, model_validator
from quart import Blueprint, Response, current_app, g, request
from quart_schema import document_response, validate_request

from api.apps.service_errors import service_error_response
from api.db.services import chunk_service, ingestion_service
from api.db.services.service_errors import Kind, ServiceError
from api.utils import reasons
from api.utils.api_utils import json_result
from api.utils.blocking import DB_EXECUTOR, DOCSTORE_EXECUTOR, PROVIDER_EXECUTOR, run_blocking
from common.settings import Settings

chunk_bp = Blueprint("chunk", __name__)

# Identical to the endpoint rows in conf/routes.yaml (Quart spells a path parameter <name>, the registry {name}).
CHUNKS = "/api/v1/datasets/<dataset_id>/documents/<doc_id>/chunks"
CHUNK = "/api/v1/datasets/<dataset_id>/documents/<doc_id>/chunks/<chunk_id>"

AUTHORIZE_TIMEOUT_SECONDS = 10.0
LIST_TIMEOUT_SECONDS = 10.0
WRITE_TIMEOUT_SECONDS = 45.0  # the embedding driver gives up after 30 s; the typed error wins over this deadline
_WHOLE_NUMBER = re.compile(r"[0-9]{1,9}")


class PositionView(BaseModel):
    page: int
    x0: int
    top: int
    x1: int
    bottom: int


class ChunkView(BaseModel):
    id: str
    text: str
    positions: list[PositionView]
    origin: str
    enabled: bool


class ChunkPage(BaseModel):
    items: list[ChunkView]
    total: int
    page_sizes: dict[str, list[float]]


class ChunkPageEnvelope(BaseModel):
    code: int
    message: str
    data: ChunkPage


class ChunkEnvelope(BaseModel):
    code: int
    message: str
    data: ChunkView


class CreateChunkBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_with_weight: str


class PatchChunkBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_with_weight: str | None = None
    available: bool | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> PatchChunkBody:
        if self.content_with_weight is None and self.available is None:
            raise ValueError("send content_with_weight or available")
        return self


def _settings() -> Settings:
    return current_app.extensions["ragflow_settings"]


def _query_invalid(message: str) -> ServiceError:
    return ServiceError(Kind.INVALID, reasons.QUERY_INVALID, message)


def _whole(name: str, default: int, low: int, high: int) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    if _WHOLE_NUMBER.fullmatch(raw) is None or not low <= int(raw) <= high:
        raise _query_invalid(f"{name} must be a whole number from {low} to {high}")
    return int(raw)


def _available() -> int | None:
    raw = request.args.get("available")
    if raw is None:
        return None
    if raw not in ("0", "1"):
        raise _query_invalid("available must be 0 or 1")
    return int(raw)


@document_response(ChunkPageEnvelope, 200)
async def list_chunks(dataset_id: str, doc_id: str) -> Response:
    try:
        settings = _settings()
        page = _whole("page", 1, 1, 1_000_000_000)
        size = _whole("size", chunk_service.DEFAULT_PAGE_SIZE, 1, chunk_service.MAX_PAGE_SIZE)
        keywords = request.args.get("keywords")
        if keywords is not None and len(keywords) > chunk_service.MAX_KEYWORDS:
            raise _query_invalid(f"keywords must be at most {chunk_service.MAX_KEYWORDS} characters")
        available = _available()
        principal = g.principal  # read on the loop: the request context does not follow the call into the worker thread
        visible = await run_blocking(DB_EXECUTOR, chunk_service.authorize_read, principal, dataset_id, timeout=AUTHORIZE_TIMEOUT_SECONDS)
        view = await run_blocking(
            DOCSTORE_EXECUTOR,
            lambda: chunk_service.list_chunks(settings, visible, doc_id, page=page, size=size, keywords=keywords, available=available),
            timeout=LIST_TIMEOUT_SECONDS,
        )
        return json_result(view)
    except ServiceError as exc:
        return service_error_response(exc)


@validate_request(CreateChunkBody)
@document_response(ChunkEnvelope, 200)
async def create_chunk(dataset_id: str, doc_id: str, data: CreateChunkBody) -> Response:
    try:
        settings = _settings()
        principal = g.principal
        text = data.content_with_weight
        visible = await run_blocking(DB_EXECUTOR, chunk_service.authorize_write, principal, dataset_id, timeout=AUTHORIZE_TIMEOUT_SECONDS)
        await run_blocking(DB_EXECUTOR, ingestion_service.write_rate_guard, settings, visible.scope.tenant_id, timeout=AUTHORIZE_TIMEOUT_SECONDS)
        made = await run_blocking(
            PROVIDER_EXECUTOR,
            lambda: chunk_service.create_chunk(settings, visible, principal, doc_id, text),
            timeout=WRITE_TIMEOUT_SECONDS,
        )
        return json_result(made)
    except ServiceError as exc:
        return service_error_response(exc)


@validate_request(PatchChunkBody)
@document_response(ChunkEnvelope, 200)
async def patch_chunk(dataset_id: str, doc_id: str, chunk_id: str, data: PatchChunkBody) -> Response:
    try:
        settings = _settings()
        principal = g.principal
        text, available = data.content_with_weight, data.available
        visible = await run_blocking(DB_EXECUTOR, chunk_service.authorize_write, principal, dataset_id, timeout=AUTHORIZE_TIMEOUT_SECONDS)
        if text is not None:  # only a text edit costs an embedding call
            await run_blocking(DB_EXECUTOR, ingestion_service.write_rate_guard, settings, visible.scope.tenant_id, timeout=AUTHORIZE_TIMEOUT_SECONDS)
        changed = await run_blocking(
            PROVIDER_EXECUTOR,
            lambda: chunk_service.update_chunk(settings, visible, principal, doc_id, chunk_id, text=text, available=available),
            timeout=WRITE_TIMEOUT_SECONDS,
        )
        return json_result(changed)
    except ServiceError as exc:
        return service_error_response(exc)


chunk_bp.add_url_rule(CHUNKS, endpoint="list_chunks", view_func=list_chunks, methods=["GET"])
chunk_bp.add_url_rule(CHUNKS, endpoint="create_chunk", view_func=create_chunk, methods=["POST"])
chunk_bp.add_url_rule(CHUNK, endpoint="patch_chunk", view_func=patch_chunk, methods=["PATCH"])
