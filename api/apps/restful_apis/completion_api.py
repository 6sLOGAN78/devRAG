"""Cited chat completion as one JSON answer or an SSE stream."""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from quart import Blueprint, Response, current_app, g
from quart_schema import document_response, validate_request

from api.apps.service_errors import error_code_for, service_error_response
from api.apps.sse_frames import DONE, delta_frame, error_frame, final_frame
from api.db.services import chat_turn_service
from api.db.services.service_errors import Kind, ServiceError
from api.utils import reasons
from api.utils.api_utils import json_result
from api.utils.blocking import DB_EXECUTOR, PROVIDER_EXECUTOR, run_blocking
from common.settings import Settings

completion_bp = Blueprint("completion", __name__)
logger = logging.getLogger(__name__)
COMPLETIONS = "/api/v1/chat/completions"
_ID = r"^[0-9a-f]{32}$"


class CompletionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chat_id: str = Field(pattern=_ID)
    session_id: str | None = Field(default=None, pattern=_ID)
    message: str
    stream: bool = True
    tenant_id: str | None = Field(default=None, pattern=_ID)


class CompletionView(BaseModel):
    answer: str
    reference: dict[str, Any]
    session_id: str
    message_id: str
    usage: dict[str, Any]
    latency_ms: int
    finish: str
    empty: bool
    notice: dict[str, int]
    final: bool


class CompletionEnvelope(BaseModel):
    code: int
    message: str
    data: CompletionView


async def _stream_body(
    plan: chat_turn_service.TurnPlan,
    first: tuple[str, str] | None,
    source: AsyncIterator[tuple[str, str]] | None,
    deadline: int,
) -> AsyncIterator[bytes]:
    pieces: list[str] = []
    settled = False
    stream_expires_at = time.monotonic() + deadline - 0.25
    try:
        await run_blocking(DB_EXECUTOR, plan.lock.renew, timeout=10)
        if plan.empty:
            yield delta_frame(plan.session_id, plan.message_id, plan.empty_text)
        else:
            if first is not None:
                pieces.append(first[1])
                yield delta_frame(plan.session_id, plan.message_id, first[1])
            if source is not None:
                while True:
                    try:
                        _kind, piece = await asyncio.wait_for(anext(source), timeout=max(0.01, stream_expires_at - time.monotonic()))
                    except StopAsyncIteration:
                        break
                    pieces.append(piece)
                    yield delta_frame(plan.session_id, plan.message_id, piece)
        await run_blocking(DB_EXECUTOR, plan.lock.renew, timeout=10)
        final = await run_blocking(PROVIDER_EXECUTOR, chat_turn_service.finalise, plan, "".join(pieces), timeout=deadline)
        await run_blocking(DB_EXECUTOR, chat_turn_service.persist_complete, plan, final, timeout=20)
        settled = True
        yield final_frame(chat_turn_service.final_view(plan, final))
        yield DONE
    except ServiceError as exc:
        await run_blocking(DB_EXECUTOR, chat_turn_service.persist_failed, plan, "".join(pieces), timeout=20)
        settled = True
        yield error_frame(error_code_for(exc), exc.message, plan.session_id, plan.message_id, exc.reason)
        yield DONE
    except TimeoutError:
        typed = ServiceError(Kind.TIMEOUT, reasons.PROVIDER_TIMEOUT, "the provider did not answer in time")
        await run_blocking(DB_EXECUTOR, chat_turn_service.persist_failed, plan, "".join(pieces), timeout=20)
        settled = True
        yield error_frame(error_code_for(typed), typed.message, plan.session_id, plan.message_id, typed.reason)
        yield DONE
    except Exception as exc:  # noqa: BLE001 - provider internals never reach the client or logs
        logger.error("chat stream failed chat=%s session=%s error=%s", plan.chat_id, plan.session_id, type(exc).__name__)
        typed = ServiceError(Kind.BAD_GATEWAY, reasons.PROVIDER_UNREACHABLE, "the provider could not be reached")
        await run_blocking(DB_EXECUTOR, chat_turn_service.persist_failed, plan, "".join(pieces), timeout=20)
        settled = True
        yield error_frame(error_code_for(typed), typed.message, plan.session_id, plan.message_id, typed.reason)
        yield DONE
    finally:
        if source is not None:
            asyncio.create_task(source.aclose())
        if not settled:
            DB_EXECUTOR.submit(chat_turn_service.persist_partial, plan, "".join(pieces))


async def _stream_response(settings: Settings, principal: Any, body: dict[str, Any]) -> Response:
    plan = await run_blocking(PROVIDER_EXECUTOR, chat_turn_service.prepare_turn, settings, principal, body, timeout=settings.chat.stream_deadline_seconds + 10)
    source: AsyncIterator[tuple[str, str]] | None = None
    first: tuple[str, str] | None = None
    if not plan.empty:
        source = chat_turn_service.events(plan)
        try:
            first = await asyncio.wait_for(anext(source, None), timeout=settings.chat.stream_deadline_seconds)
        except ServiceError:
            await run_blocking(DB_EXECUTOR, chat_turn_service.persist_failed, plan, "", timeout=20)
            raise
        except TimeoutError:
            await run_blocking(DB_EXECUTOR, chat_turn_service.persist_failed, plan, "", timeout=20)
            raise ServiceError(Kind.TIMEOUT, reasons.PROVIDER_TIMEOUT, "the provider did not answer in time") from None
        except BaseException:
            DB_EXECUTOR.submit(chat_turn_service.persist_partial, plan, "")
            raise
    response = Response(
        _stream_body(plan, first, source, settings.chat.stream_deadline_seconds),
        content_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
    response.timeout = settings.chat.stream_deadline_seconds
    return response


@validate_request(CompletionBody)
@document_response(CompletionEnvelope, 200)
async def complete(data: CompletionBody) -> Response:
    try:
        settings: Settings = current_app.extensions["ragflow_settings"]
        principal = g.principal
        if data.stream:
            return await _stream_response(settings, principal, data.model_dump())
        view = await chat_turn_service.async_complete_turn(settings, principal, data.model_dump())
        return json_result(view)
    except ServiceError as exc:
        return service_error_response(exc)


completion_bp.add_url_rule(COMPLETIONS, endpoint="complete", view_func=complete, methods=["POST"])
