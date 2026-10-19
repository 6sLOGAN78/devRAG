"""Chat assistant routes under ``/api/v1/chats`` (plan 05-08; CHAT-01..07, D-08..D-11, D-19, D-23..D-26).

Five thin handlers over :mod:`api.db.services.dialog_service`, laid out like the dataset routes: bodies refuse every field they do not name, an update
applies only the keys that were sent (``model_fields_set`` tells an absent key from ``null``), the blocking service call runs in the bounded database
pool, and a typed ``ServiceError`` is mapped to the envelope. There is no permission-matrix area for chats (R-199): who may see, edit or delete an
assistant is decided in the service from the assistant row (creator, ``permission``, and the caller's role for a ``team`` assistant), so an absent id,
another workspace's id and another member's private assistant are the one 404 body whoever asks (D-19, D-20).

The one exception to a bare 404 is a dataset that cannot be bound: the service says ``dataset_not_found`` and this module keeps that reason in
``data.reason`` so the app can mark the Datasets field (R-210, R-211). An assistant miss stays bare.
"""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from quart import Blueprint, Response, g, request
from quart_schema import document_response, validate_request

from api.apps.handler_support import acting_scope
from api.apps.service_errors import not_found_response, service_error_response
from api.db.services import dialog_service
from api.db.services.dialog_rules import invalid
from api.db.services.service_errors import Kind, ServiceError
from api.utils import reasons
from api.utils.api_utils import error_result, json_result
from api.utils.blocking import DB_EXECUTOR, run_blocking
from common.constants import RetCode

chat_bp = Blueprint("chat", __name__)

# Identical to the endpoint rows in conf/routes.yaml (Quart spells a path parameter <name>, the registry {name}).
CHATS = "/api/v1/chats"
CHAT = "/api/v1/chats/<chat_id>"

LOOKUP_TIMEOUT_SECONDS = 10.0
WRITE_TIMEOUT_SECONDS = 20.0  # a create or rename waits up to 10 s for the creation lock, then validates models and writes
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
MAX_KEYWORDS = 128
_TENANT_ID_PATTERN = r"^[0-9a-f]{32}$"
_WHOLE_NUMBER = re.compile(r"[0-9]{1,9}")


class CreateChatBody(BaseModel):
    """Only these fields exist. Their bounds are the service's, so a bad value is a typed ``fields_invalid`` and a missing or unknown model is ``model_unavailable``."""

    model_config = ConfigDict(extra="forbid")

    name: str
    icon: str | None = None
    permission: str = "me"
    kb_ids: list[str] = Field(default_factory=list)
    llm_id: str | None = None
    rerank_id: str | None = None
    similarity_threshold: float | None = None
    vector_similarity_weight: float | None = None
    top_n: int | None = None
    prompt_config: dict[str, Any] | None = None
    llm_setting: dict[str, Any] | None = None
    tenant_id: str | None = Field(default=None, pattern=_TENANT_ID_PATTERN)


class UpdateChatBody(BaseModel):
    """The editable fields. A key that is absent is not a change; an explicit null clears ``icon`` and ``rerank_id`` and is refused for the rest."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    icon: str | None = None
    permission: str | None = None
    kb_ids: list[str] | None = None
    llm_id: str | None = None
    rerank_id: str | None = None
    similarity_threshold: float | None = None
    vector_similarity_weight: float | None = None
    top_n: int | None = None
    prompt_config: dict[str, Any] | None = None
    llm_setting: dict[str, Any] | None = None


class PromptConfigView(BaseModel):
    system: str
    prologue: str
    empty_response: str


class AssistantView(BaseModel):
    id: str
    name: str
    icon: str | None = None
    permission: str
    created_by: str
    kb_ids: list[str]
    unavailable_datasets: int
    members_with_chats: int | None = None
    llm_id: str
    rerank_id: str
    similarity_threshold: float
    vector_similarity_weight: float
    top_n: int
    prompt_config: PromptConfigView
    llm_setting: dict[str, Any]
    update_time: int


class AssistantEnvelope(BaseModel):
    code: int
    message: str
    data: AssistantView


class AssistantPage(BaseModel):
    items: list[AssistantView]
    total: int


class AssistantPageEnvelope(BaseModel):
    code: int
    message: str
    data: AssistantPage


class DeletedAssistant(BaseModel):
    deleted: str


class DeletedAssistantEnvelope(BaseModel):
    code: int
    message: str
    data: DeletedAssistant


def _failure(exc: ServiceError) -> Response:
    """The shared mapping, except that a dataset which cannot be bound keeps its reason (an assistant miss is the bare 404)."""
    if exc.kind is Kind.NOT_FOUND and exc.reason == reasons.DATASET_NOT_FOUND:
        return error_result(RetCode.NOT_FOUND, "not found", 404, data={"reason": reasons.DATASET_NOT_FOUND})
    return service_error_response(exc)


def _whole(name: str, default: int, low: int, high: int) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    if _WHOLE_NUMBER.fullmatch(raw) is None or not low <= int(raw) <= high:
        raise invalid(f"{name} must be a whole number from {low} to {high}")
    return int(raw)


@validate_request(CreateChatBody)
@document_response(AssistantEnvelope, 200)
async def create_chat(data: CreateChatBody) -> Response:
    try:
        scope = await acting_scope(data.tenant_id)
        if scope is None:
            return not_found_response()
        body = {name: getattr(data, name) for name in data.model_fields_set if name != "tenant_id"}
        principal = g.principal
        view = await run_blocking(DB_EXECUTOR, dialog_service.create_assistant, principal, scope, body, timeout=WRITE_TIMEOUT_SECONDS)
        return json_result(view)
    except ServiceError as exc:
        return _failure(exc)


@document_response(AssistantPageEnvelope, 200)
async def list_chats() -> Response:
    try:
        scope = await acting_scope(request.args.get("tenant_id"))
        if scope is None:
            return not_found_response()
        page = _whole("page", 1, 1, 1_000_000_000)
        page_size = _whole("page_size", DEFAULT_PAGE_SIZE, 1, MAX_PAGE_SIZE)
        keywords = request.args.get("keywords")
        if keywords is not None and len(keywords) > MAX_KEYWORDS:
            raise invalid(f"keywords must be at most {MAX_KEYWORDS} characters")
        principal = g.principal  # read on the loop: the request context does not follow the call into the worker thread
        items, total = await run_blocking(
            DB_EXECUTOR,
            lambda: dialog_service.list_assistants(principal, scope, page, page_size, keywords),
            timeout=LOOKUP_TIMEOUT_SECONDS,
        )
        return json_result({"items": items, "total": total})
    except ServiceError as exc:
        return _failure(exc)


@document_response(AssistantEnvelope, 200)
async def get_chat(chat_id: str) -> Response:
    try:
        view = await run_blocking(DB_EXECUTOR, dialog_service.get_assistant, g.principal, chat_id, timeout=LOOKUP_TIMEOUT_SECONDS)
        return json_result(view)
    except ServiceError as exc:
        return _failure(exc)


@validate_request(UpdateChatBody)
@document_response(AssistantEnvelope, 200)
async def update_chat(chat_id: str, data: UpdateChatBody) -> Response:
    try:
        changes = {name: getattr(data, name) for name in data.model_fields_set}
        view = await run_blocking(DB_EXECUTOR, dialog_service.update_assistant, g.principal, chat_id, changes, timeout=WRITE_TIMEOUT_SECONDS)
        return json_result(view)
    except ServiceError as exc:
        return _failure(exc)


@document_response(DeletedAssistantEnvelope, 200)
async def delete_chat(chat_id: str) -> Response:
    try:
        deleted = await run_blocking(DB_EXECUTOR, dialog_service.delete_assistant, g.principal, chat_id, timeout=WRITE_TIMEOUT_SECONDS)
        return json_result({"deleted": deleted})
    except ServiceError as exc:
        return _failure(exc)


chat_bp.add_url_rule(CHATS, endpoint="create_chat", view_func=create_chat, methods=["POST"])
chat_bp.add_url_rule(CHATS, endpoint="list_chats", view_func=list_chats, methods=["GET"])
chat_bp.add_url_rule(CHAT, endpoint="get_chat", view_func=get_chat, methods=["GET"])
chat_bp.add_url_rule(CHAT, endpoint="update_chat", view_func=update_chat, methods=["PUT"])
chat_bp.add_url_rule(CHAT, endpoint="delete_chat", view_func=delete_chat, methods=["DELETE"])
