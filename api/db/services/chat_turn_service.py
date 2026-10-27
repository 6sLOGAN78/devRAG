"""One cited chat turn, shared by the completion and streaming routes."""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import time
import uuid
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

from api.db.database import DB
from api.db.models import Knowledgebase
from api.db.services import conversation_service, dialog_service, retrieval_service, tenant_llm_service
from api.db.services.auth_service import Principal
from api.db.services.chat_turn_reference import insert_missing, reference
from api.db.services.knowledgebase_service import embedding_dimensions
from api.db.services.llm_service import LLMBundle, split_usage
from api.db.services.service_errors import Kind, ServiceError
from api.utils import reasons
from api.utils.blocking import DB_EXECUTOR, PROVIDER_EXECUTOR, run_blocking
from common.settings import Settings
from rag.llm.model_meta import lookup
from rag.llm.stream import Usage
from rag.llm.sync_loop import PrivateLoop
from rag.nlp.search import Hit
from rag.nlp.token_count import count_tokens
from rag.prompts.citations import canonicalise, valid_indices
from rag.prompts.generator import CITATION_RULES, ContextChunk, Prompt, assemble_prompt, build_context, token_budget, trim_history

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TurnPlan:
    chat_id: str
    session_id: str
    message_id: str
    tenant_id: str
    user_id: str
    dataset_ids: tuple[str, ...]
    empty: bool
    empty_text: str
    used_chunks: tuple[Hit, ...]
    prompt: Prompt
    gen_conf: dict[str, Any]
    bundle: LLMBundle | None
    lock: conversation_service.TurnLock
    started_at: float
    notice: dict[str, int]
    used_embedder: LLMBundle | None
    settings: Settings


@dataclass(frozen=True)
class FinalMessage:
    answer: str
    reference: dict[str, Any]
    usage: dict[str, Any]
    latency_ms: int
    finish: str
    empty: bool


def _embedding_bundle(settings: Settings, tenant_id: str, dataset_id: str) -> LLMBundle:
    with DB.connection_context():
        row = Knowledgebase.select(Knowledgebase.embd_id).where(Knowledgebase.id == dataset_id).first()
    if row is None:
        raise ServiceError(Kind.CONFLICT, reasons.DATASETS_UNAVAILABLE, "the bound datasets are unavailable")
    dimensions = embedding_dimensions(tenant_id)
    dimension = dimensions.get(row.embd_id)
    if dimension is None:
        raise ServiceError(Kind.CONFLICT, reasons.MODEL_UNAVAILABLE, "that model is not available in this workspace")
    return LLMBundle(tenant_id, row.embd_id, "embedding", settings=settings, expected_dimension=dimension)


def _chunk(hit: Hit) -> ContextChunk:
    page = hit.page_num_int[0] if hit.page_num_int and isinstance(hit.page_num_int[0], int) else None
    return ContextChunk(
        hit.chunk_id, hit.doc_id, hit.doc_name, hit.dataset_id, page, hit.content,
        hit.similarity, hit.term_similarity, hit.vector_similarity, hit.rerank_similarity, hit.position_int, hit.page_dims_flt,
    )


def _prompt(assistant: Any, history: list[dict[str, Any]], question: str, hits: list[Hit], model: LLMBundle) -> tuple[Prompt, tuple[Hit, ...]]:
    meta = lookup(model.provider, model.model)
    completion = min(int(assistant.llm_setting["max_tokens"]), meta.max_completion_tokens)
    instruction = assistant.prompt_config.get("system", "")
    base = count_tokens(instruction) + count_tokens(CITATION_RULES) + count_tokens(question)
    context_budget = token_budget(meta.max_tokens, base, 0, completion)
    built = build_context([_chunk(hit) for hit in hits], context_budget)
    retained = {chunk.chunk_id for chunk in built.used}
    used_hits = tuple(hit for hit in hits if hit.chunk_id in retained)
    history_budget = token_budget(meta.max_tokens, base, count_tokens(built.text), completion)
    trimmed = trim_history(history, history_budget)
    return assemble_prompt(instruction, built.text, trimmed, question, assistant.llm_setting), used_hits


def prepare_turn(settings: Settings, principal: Principal, request: Mapping[str, Any]) -> TurnPlan:
    """Validate, authorise, guard, store the question, then prepare retrieval and model work."""
    started_at = time.monotonic()
    raw = request.get("message")
    question = raw.strip() if isinstance(raw, str) else ""
    if not question or len(question) > settings.chat.max_question_chars:
        raise ServiceError(Kind.INVALID, reasons.QUESTION_INVALID, "question is empty or too long")
    chat_id = request.get("chat_id")
    binding = dialog_service.resolve_for_chat(principal, chat_id)
    assistant = binding.assistant
    if request.get("tenant_id") is not None and request["tenant_id"] != binding.tenant_id:
        raise ServiceError(Kind.NOT_FOUND, reasons.ASSISTANT_NOT_FOUND, "not found")
    if assistant.kb_ids and not binding.usable_dataset_ids:
        raise ServiceError(Kind.CONFLICT, reasons.DATASETS_UNAVAILABLE, "the bound datasets are unavailable")
    session_id = request.get("session_id")
    if session_id is None:
        session = conversation_service.create_session(principal, chat_id, question[:60])
        session_id = session["id"]
    else:
        conversation_service.get_session(principal, chat_id, session_id, limit=1)
    conversation_service.chat_rate_guard(settings, binding.tenant_id, principal.user_id)
    lock = conversation_service.acquire_turn(settings, session_id)
    try:
        _user_message_id, history = conversation_service.append_user_message(principal, chat_id, session_id, question, settings.chat)
        message_id = uuid.uuid4().hex
        notice = {"unavailable_datasets": binding.unavailable_count}
        empty = False
        hits: list[Hit] = []
        if binding.usable_dataset_ids:
            found = retrieval_service.retrieve_for_chat(settings, assistant, binding.tenant_id, binding.usable_dataset_ids, question)
            hits = found.hits
            empty = not hits
        if empty:
            lock.renew()
            return TurnPlan(chat_id, session_id, message_id, binding.tenant_id, principal.user_id, tuple(binding.usable_dataset_ids), True,
                            assistant.prompt_config["empty_response"], (), Prompt("", []), {}, None, lock, started_at, notice, None, settings)
        try:
            bundle = LLMBundle(binding.tenant_id, assistant.llm_id, "chat", settings=settings)
        except ServiceError as exc:
            if exc.reason == reasons.MODEL_UNAVAILABLE:
                raise ServiceError(Kind.CONFLICT, reasons.MODEL_UNAVAILABLE, "that model is not available in this workspace") from None
            raise
        prompt, used = _prompt(assistant, history, question, hits, bundle)
        embedder = _embedding_bundle(settings, binding.tenant_id, binding.usable_dataset_ids[0]) if used else None
        lock.renew()
        return TurnPlan(chat_id, session_id, message_id, binding.tenant_id, principal.user_id, tuple(binding.usable_dataset_ids), False,
                        assistant.prompt_config["empty_response"], used, prompt, dict(assistant.llm_setting), bundle, lock, started_at, notice, embedder, settings)
    except BaseException:
        lock.release()
        raise


async def events(plan: TurnPlan) -> AsyncIterator[tuple[str, str]]:
    """Yield provider deltas; persistence belongs to the caller."""
    if plan.empty or plan.bundle is None:
        return
    async for piece in plan.bundle.async_chat_streamly(plan.prompt.system, plan.prompt.messages, plan.gen_conf):
        yield "delta", piece


def _usage(provider: Usage | None, prompt: Prompt, answer: str) -> dict[str, Any]:
    if provider is None:
        incoming = count_tokens(prompt.system) + sum(count_tokens(message["content"]) for message in prompt.messages)
        outgoing = count_tokens(answer)
        return {"input": incoming, "output": outgoing, "total": incoming + outgoing, "estimated": True}
    incoming, outgoing, total = split_usage(provider)
    return {"input": incoming, "output": outgoing, "total": total, "estimated": provider.estimated}


def estimate_usage(plan: TurnPlan, text: str) -> dict[str, Any]:
    """A stopped turn has no provider total, so count the prompt and retained answer."""
    return _usage(None, plan.prompt, text)


def finalise(plan: TurnPlan, full_text: str, usage: Usage | None = None) -> FinalMessage:
    if plan.empty:
        return FinalMessage(plan.empty_text, reference(()), {"input": 0, "output": 0, "total": 0, "estimated": False},
                            max(0, int((time.monotonic() - plan.started_at) * 1000)), "complete", True)
    answer = canonicalise(full_text, len(plan.used_chunks))
    inserted = False
    if answer.strip() and not valid_indices(answer, len(plan.used_chunks)):
        answer, inserted = insert_missing(plan, answer)
    counted = _usage(usage if usage is not None else plan.bundle.last_usage if plan.bundle else None, plan.prompt, answer)
    if inserted:
        counted["citations"] = "inserted"
    return FinalMessage(answer, reference(plan.used_chunks), counted, max(0, int((time.monotonic() - plan.started_at) * 1000)), "complete", False)


def _store(plan: TurnPlan, final: FinalMessage) -> None:
    message = {
        "id": plan.message_id, "role": "assistant", "content": final.answer, "reference": final.reference,
        "finish": final.finish, "usage": final.usage, "latency_ms": final.latency_ms, "empty": final.empty,
        "created_at": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
    }
    try:
        conversation_service.replace_assistant_message(plan.session_id, plan.message_id, message)
    except ServiceError as exc:
        if exc.kind is not Kind.NOT_FOUND:
            raise
        conversation_service.append_assistant_message(plan.session_id, message)


def persist_complete(plan: TurnPlan, final: FinalMessage) -> None:
    try:
        _store(plan, final)
    finally:
        plan.lock.release()


def persist_partial(plan: TurnPlan, text: str, estimated_usage: Usage | None = None) -> None:
    answer = canonicalise(text, len(plan.used_chunks))
    cited = set(valid_indices(answer, len(plan.used_chunks)))
    usage = _usage(estimated_usage, plan.prompt, answer) if estimated_usage is not None else estimate_usage(plan, answer)
    usage["estimated"] = True
    final = FinalMessage(answer, reference(plan.used_chunks, cited), usage,
                         max(0, int((time.monotonic() - plan.started_at) * 1000)), "stopped", False)
    try:
        _store(plan, final)
        if plan.bundle is not None and not getattr(plan.lock, "usage_recorded", False):
            try:
                tenant_llm_service.add_used_tokens(plan.tenant_id, plan.bundle.provider, plan.bundle.model, usage["total"])
                plan.lock.usage_recorded = True
            except Exception as exc:  # noqa: BLE001 - losing a counter cannot lose a stopped answer
                logger.error("stopped turn usage not recorded tenant=%s chat=%s error=%s", plan.tenant_id, plan.chat_id, type(exc).__name__)
    finally:
        plan.lock.release()


def persist_failed(plan: TurnPlan, text: str = "") -> None:
    answer = canonicalise(text, len(plan.used_chunks))
    cited = set(valid_indices(answer, len(plan.used_chunks)))
    final = FinalMessage(answer, reference(plan.used_chunks, cited), estimate_usage(plan, answer),
                         max(0, int((time.monotonic() - plan.started_at) * 1000)), "failed", False)
    try:
        _store(plan, final)
    finally:
        plan.lock.release()


def final_view(plan: TurnPlan, final: FinalMessage) -> dict[str, Any]:
    return {
        "answer": final.answer, "reference": final.reference, "session_id": plan.session_id, "message_id": plan.message_id,
        "usage": final.usage, "latency_ms": final.latency_ms, "finish": final.finish, "empty": final.empty,
        "notice": plan.notice, "final": True,
    }


async def async_complete_turn(settings: Settings, principal: Principal, request: Mapping[str, Any]) -> dict[str, Any]:
    plan = await run_blocking(PROVIDER_EXECUTOR, prepare_turn, settings, principal, request,
                              timeout=settings.chat.stream_deadline_seconds + 10)
    try:
        async def collect() -> str:
            pieces: list[str] = []
            async for _kind, piece in events(plan):
                pieces.append(piece)
            return "".join(pieces)

        answer = await asyncio.wait_for(collect(), timeout=settings.chat.stream_deadline_seconds) if not plan.empty else ""
        await run_blocking(DB_EXECUTOR, plan.lock.renew, timeout=10)
        final = await run_blocking(PROVIDER_EXECUTOR, finalise, plan, answer, timeout=settings.chat.stream_deadline_seconds)
        await run_blocking(DB_EXECUTOR, persist_complete, plan, final, timeout=20)
        return final_view(plan, final)
    except BaseException as exc:
        try:
            await run_blocking(DB_EXECUTOR, persist_failed, plan, timeout=20)
        finally:
            if isinstance(exc, ServiceError):
                raise
            if isinstance(exc, TimeoutError):
                raise ServiceError(Kind.TIMEOUT, reasons.PROVIDER_TIMEOUT, "the provider did not answer in time") from None
        raise


def complete_turn(settings: Settings, principal: Principal, request: Mapping[str, Any]) -> dict[str, Any]:
    """Synchronous entry point for callers outside an event loop."""
    loop = PrivateLoop()
    try:
        return loop.run(async_complete_turn(settings, principal, request))
    finally:
        loop.close()
