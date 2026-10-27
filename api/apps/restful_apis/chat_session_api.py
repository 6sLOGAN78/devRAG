"""Per-user chat sessions and feedback over HTTP (plan 05-09)."""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from quart import Blueprint, Response, current_app, g, request
from quart_schema import document_response, validate_request

from api.apps.service_errors import service_error_response
from api.db.services import conversation_service
from api.db.services.service_errors import Kind, ServiceError
from api.utils import reasons
from api.utils.api_utils import json_result
from api.utils.blocking import DB_EXECUTOR, run_blocking
from common.settings import Settings

chat_session_bp = Blueprint("chat_session", __name__)

SESSIONS = "/api/v1/chats/<chat_id>/sessions"
SESSION = SESSIONS + "/<session_id>"
FEEDBACK = SESSION + "/messages/<message_id>/feedback"
LOOKUP_TIMEOUT_SECONDS = 10.0
WRITE_TIMEOUT_SECONDS = 20.0
_WHOLE_NUMBER = re.compile(r"[0-9]{1,9}")


class CreateSessionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None


class FeedbackBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    thumb: Literal["up", "down"] | None
    comment: str | None = None


class SessionView(BaseModel):
    id: str
    chat_id: str
    name: str
    create_time: int
    update_time: int


class SessionDetail(SessionView):
    messages: list[dict[str, Any]]
    has_earlier: bool


class SessionEnvelope(BaseModel):
    code: int
    message: str
    data: SessionDetail


class SessionPage(BaseModel):
    items: list[SessionView]
    total: int


class SessionPageEnvelope(BaseModel):
    code: int
    message: str
    data: SessionPage


class DeletedSession(BaseModel):
    deleted: str


class DeletedSessionEnvelope(BaseModel):
    code: int
    message: str
    data: DeletedSession


class FeedbackView(BaseModel):
    message_id: str
    feedback: Literal["up", "down"] | None


class FeedbackEnvelope(BaseModel):
    code: int
    message: str
    data: FeedbackView


def _whole(name: str, default: int, low: int, high: int) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    if _WHOLE_NUMBER.fullmatch(raw) is None or not low <= int(raw) <= high:
        raise ServiceError(Kind.INVALID, reasons.FIELDS_INVALID, f"{name} must be a whole number from {low} to {high}")
    return int(raw)


@validate_request(CreateSessionBody)
@document_response(SessionEnvelope, 200)
async def create_session(chat_id: str, data: CreateSessionBody) -> Response:
    try:
        principal = g.principal
        view = await run_blocking(DB_EXECUTOR, conversation_service.create_session, principal, chat_id, data.name, timeout=WRITE_TIMEOUT_SECONDS)
        return json_result(view)
    except ServiceError as exc:
        return service_error_response(exc)


@document_response(SessionPageEnvelope, 200)
async def list_sessions(chat_id: str) -> Response:
    try:
        page = _whole("page", 1, 1, 1_000_000)
        page_size = _whole("page_size", 20, 1, 100)
        principal = g.principal
        view = await run_blocking(DB_EXECUTOR, conversation_service.list_sessions, principal, chat_id, page, page_size, timeout=LOOKUP_TIMEOUT_SECONDS)
        return json_result(view)
    except ServiceError as exc:
        return service_error_response(exc)


@document_response(SessionEnvelope, 200)
async def get_session(chat_id: str, session_id: str) -> Response:
    try:
        settings: Settings = current_app.extensions["ragflow_settings"]
        limit = _whole("limit", settings.chat.message_page_size, 1, 200)
        before = request.args.get("before")
        principal = g.principal
        view = await run_blocking(DB_EXECUTOR, conversation_service.get_session, principal, chat_id, session_id, before, limit, timeout=LOOKUP_TIMEOUT_SECONDS)
        return json_result(view)
    except ServiceError as exc:
        return service_error_response(exc)


@document_response(DeletedSessionEnvelope, 200)
async def delete_session(chat_id: str, session_id: str) -> Response:
    try:
        principal = g.principal
        view = await run_blocking(DB_EXECUTOR, conversation_service.delete_session, principal, chat_id, session_id, timeout=WRITE_TIMEOUT_SECONDS)
        return json_result(view)
    except ServiceError as exc:
        return service_error_response(exc)


@validate_request(FeedbackBody)
@document_response(FeedbackEnvelope, 200)
async def set_feedback(chat_id: str, session_id: str, message_id: str, data: FeedbackBody) -> Response:
    try:
        principal = g.principal
        view = await run_blocking(
            DB_EXECUTOR, conversation_service.set_feedback, principal, chat_id, session_id, message_id, data.thumb, data.comment, timeout=WRITE_TIMEOUT_SECONDS
        )
        return json_result(view)
    except ServiceError as exc:
        return service_error_response(exc)


chat_session_bp.add_url_rule(SESSIONS, endpoint="create_session", view_func=create_session, methods=["POST"])
chat_session_bp.add_url_rule(SESSIONS, endpoint="list_sessions", view_func=list_sessions, methods=["GET"])
chat_session_bp.add_url_rule(SESSION, endpoint="get_session", view_func=get_session, methods=["GET"])
chat_session_bp.add_url_rule(SESSION, endpoint="delete_session", view_func=delete_session, methods=["DELETE"])
chat_session_bp.add_url_rule(FEEDBACK, endpoint="set_feedback", view_func=set_feedback, methods=["POST"])
