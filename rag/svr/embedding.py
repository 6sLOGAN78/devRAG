"""Embedding off the caller's thread, abandonable on cancel (ING-13..15, D-06).

The provider call runs on a small pool of ``embed`` threads. The caller waits with :func:`rag.svr.control.wait_for`, so a cancel is noticed within
the poll period even in the middle of a blocking call; the call is abandoned and its result discarded. The database connection of the worker thread is
closed before the provider call and is reopened by each short operation afterwards, so inference never holds a pooled connection (ING-15).
"""

from __future__ import annotations

import threading
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor

from api.db.database import DB
from api.db.services.llm_service import LLMBundle
from api.db.services.task_service import TaskContext
from common.settings import Settings
from rag.svr.control import TaskControl, wait_for
from rag.svr.limiters import Limiters


def release_database_connection() -> None:
    """Close this thread's pooled connection if it holds one."""
    if not DB.is_closed():
        DB.close()


class EmbedRunner:
    def __init__(self, settings: Settings, limiters: Limiters) -> None:
        self._settings = settings
        self._limiters = limiters
        self._pool: ThreadPoolExecutor | None = None
        self._bundles: dict[str, LLMBundle] = {}
        self._lock = threading.Lock()

    def _executor(self) -> ThreadPoolExecutor:
        with self._lock:
            if self._pool is None:
                self._pool = ThreadPoolExecutor(max_workers=self._settings.ingest.embed_concurrency, thread_name_prefix="embed")
            return self._pool

    def _bundle(self, ctx: TaskContext, dimension: int) -> LLMBundle:
        with self._lock:
            cached = self._bundles.get(ctx.task_id)
        if cached is not None:
            return cached
        # Built from the dataset row's tenant and model only (T-04-11-07); get_credential opens its own connection context.
        made = LLMBundle(ctx.tenant_id, ctx.embd_id, "embedding", settings=self._settings, expected_dimension=dimension)
        with self._lock:
            self._bundles[ctx.task_id] = made
        return made

    def _encode_blocking(self, texts: list[str], ctx: TaskContext, dimension: int) -> list[list[float]]:
        with self._limiters.embed_limiter:
            bundle = self._bundle(ctx, dimension)
            release_database_connection()
            if ctx.parser_id in {"one", "manual", "qa", "book", "paper", "laws", "presentation", "table", "picture", "audio", "email", "resume"}:
                from rag.nlp.token_count import count_tokens
                from rag.svr.failure import TaskFailure

                if any(count_tokens(text) > bundle.token_limit for text in texts):
                    raise TaskFailure("embed", "chunk_too_long")
            vectors, _ = bundle.encode(texts)
        return vectors

    def encode(self, texts: list[str], ctx: TaskContext, control: TaskControl, dimension: int) -> list[list[float]]:
        release_database_connection()
        future = self._executor().submit(self._encode_blocking, texts, ctx, dimension)
        return wait_for(future, control)

    def describe_image(self, image: bytes, model_id: str, ctx: TaskContext, control: TaskControl) -> str:
        def describe():
            release_database_connection()
            with self._limiters.embed_limiter:
                control.check()
                bundle = LLMBundle(ctx.tenant_id,model_id,"vision",settings=self._settings)
                control.check()
                return bundle.describe(image)
        control.check()
        result = wait_for(self._executor().submit(describe),control)
        control.check()
        return result

    def transcribe_audio(self, content: bytes, model_id: str, ctx: TaskContext, control: TaskControl, language: str | None = None):
        def transcribe():
            release_database_connection()
            with self._limiters.embed_limiter:
                control.check()
                bundle = LLMBundle(ctx.tenant_id, model_id, "asr", settings=self._settings)
                control.check()
                return bundle.transcribe(content, language)
        control.check()
        result = wait_for(self._executor().submit(transcribe), control)
        control.check()
        return result

    def extract_resume(self, texts: list[str], model_id: str, ctx: TaskContext, control: TaskControl) -> str:
        from rag.svr.enrichment import resume_completion

        def extract():
            release_database_connection()
            with self._limiters.embed_limiter:
                control.check()
                # One physical request: no automatic transport retry or JSON repair.
                settings = replace(self._settings, llm=replace(self._settings.llm, max_retries=0))
                bundle = LLMBundle(ctx.tenant_id, model_id, "chat", settings=settings)
                control.check()
                return resume_completion(bundle, texts)
        control.check()
        release_database_connection()
        result = wait_for(self._executor().submit(extract), control)
        control.check()
        return result

    def forget(self, task_id: str) -> None:
        with self._lock:
            self._bundles.pop(task_id, None)

    def close(self) -> None:
        with self._lock:
            pool, self._pool = self._pool, None
            self._bundles.clear()
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)
