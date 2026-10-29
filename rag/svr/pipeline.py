"""One task: fetch, parse, chunk, embed, bulk index (ING-09, ING-13..15, CHUNK-16, IDX-01..03, IDX-07, DOC-20; R-155, R-158, D-05, D-26).

``run_pipeline`` is synchronous: the executor (plan 04-12) calls it on a worker thread, owns ``task_limiter`` and the final ``mark_task_done`` or
failure line. Inside, blocking work sits behind ``minio_limiter`` (storage), ``chunk_limiter`` (parse and chunk) and the embedding pool
(``embed_limiter``). ``kg_limiter`` is not used by any stage. Every exception is classified once, at the step boundary, by ``failure.classify``.
The database connection is released before each long call and reopened by each short operation.
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path

from api.db.services import document_asset_service, task_service, tenant_model_service
from api.db.services.task_service import TaskContext
from common.constants import BUCKET_NAME
from common.doc_store.doc_store_base import DocStoreConnection, index_name
from common.ingest_codes import RUN_CANCELLED
from common.settings import Settings
from rag.chunking.factory import get_chunker, get_chunker_config
from rag.chunking.types import Chunk
from rag.parsers.pdf import thumbnail_data_url
from rag.parsers.router import parser_for_suffix
from rag.parsers.types import ParseLimits, ParseReport, SourceFile
from rag.svr.chunk_doc import build_row, l2_normalize, parsed_chunk_id
from rag.svr.control import LockLost, TaskCancelled, TaskControl
from rag.svr.embedding import EmbedRunner, release_database_connection
from rag.svr.failure import TaskFailure, classify
from rag.svr.limiters import Limiters
from rag.utils.storage_base import Storage

logger = logging.getLogger(__name__)

PARSED_PROGRESS = 0.1
READ_CHUNK = 1 << 20


@dataclass(frozen=True)
class PipelineDeps:
    settings: Settings
    storage: Storage
    doc_store: DocStoreConnection
    embedder: EmbedRunner
    limiters: Limiters


@dataclass(frozen=True)
class PipelineResult:
    chunk_ids: tuple[str, ...]
    chunk_count: int
    pages_total: int
    pages_without_text: int
    images_skipped: int


@contextmanager
def _step(name: str, ctx: TaskContext) -> Iterator[None]:
    """Turn any exception of this step into a ``TaskFailure``; cancel and lock loss pass through. Only the class name is logged."""
    try:
        yield
    except (TaskCancelled, LockLost):
        raise
    except Exception as exc:
        failure = classify(exc, name)
        logger.warning("task step failed", extra={"task": ctx.task_id, "step": failure.step, "code": failure.code, "error_type": type(exc).__name__})
        raise failure from None


def _embedding_dimension(ctx: TaskContext) -> int:
    for model in tenant_model_service.list_models(ctx.tenant_id, "embedding"):
        if model.composite == ctx.embd_id and isinstance(model.dimension, int):
            return model.dimension
    raise TaskFailure("embed", "model_unavailable")


def _fetch(ctx: TaskContext, deps: PipelineDeps, directory: Path) -> Path:
    target = directory / f"source.{ctx.doc_suffix.lower().lstrip('.') or 'bin'}"
    with deps.limiters.minio_limiter:
        stream = deps.storage.iter_chunks(BUCKET_NAME, ctx.doc_location, READ_CHUNK)
        try:
            with target.open("wb") as out:
                for block in stream:
                    out.write(block)
        finally:
            close = getattr(stream, "close", None)
            if close is not None:
                close()
    return target


def _parse_and_chunk(ctx: TaskContext, deps: PipelineDeps, control: TaskControl, path: Path, report: ParseReport) -> list[Chunk]:
    spec = parser_for_suffix(ctx.doc_suffix)
    chunker = get_chunker(ctx.parser_id)
    if ctx.parser_id == "qa" and spec.name not in {"txt", "csv", "json", "xlsx"}:
        from rag.parsers.errors import UnsupportedType

        raise UnsupportedType()
    limits = ParseLimits(xlsx_max_cells=deps.settings.ingest.xlsx_max_cells)
    source = SourceFile(path, ctx.doc_suffix.lower().lstrip("."), path.stat().st_size)
    page_range = (ctx.from_page, ctx.to_page) if spec.name == "pdf" else None
    chunks: list[Chunk] = []
    assets = []
    generation = document_asset_service.current_generation(ctx) if deps.settings.deepdoc.url and spec.name in {"pdf", "docx", "pptx"} else None

    def text_blocks(blocks):
        # Assets are normalized remotely already; persist once and substitute opaque ids before chunking.
        materialized = list(blocks)
        for block in materialized:
            control.check()
            assets.extend(block.assets)
            if len(assets) > 128 or sum(len(asset.content) for asset in assets) > 24 * 1024 * 1024:
                from rag.parsers.errors import FileTooLarge

                raise FileTooLarge()
        unique = {(a.kind, a.sha256): a for a in assets}
        with deps.limiters.minio_limiter:
            ids = document_asset_service.persist_assets(deps.settings, ctx, generation, list(unique.values()), control, storage=deps.storage)
        asset_ids = dict(zip(unique, ids, strict=True))
        for block in materialized:
            control.check()
            table = block.table
            if table is not None and table.asset_sha256:
                table = replace(table, asset_id=asset_ids[("table", table.asset_sha256)])
            owned_ids = tuple(dict.fromkeys((*block.image_ids, *(asset_ids[(a.kind, a.sha256)] for a in block.assets))))
            yield replace(block, assets=(), table=table, image_ids=owned_ids)

    with deps.limiters.chunk_limiter:
        options = {"settings": deps.settings, "parser_config": ctx.parser_config} if spec.name == "pdf" else ({"settings": deps.settings} if spec.name in {"docx", "pptx"} else {})
        if ctx.parser_id == "table" and spec.name in {"csv", "xlsx"}:
            options["structured_tables"] = True
            if spec.name == "csv":
                options["table_title"] = ctx.doc_name.rsplit(".", 1)[0]
        if ctx.parser_id == "qa" and spec.name == "xlsx":
            options["structured_records"] = True
        if ctx.parser_id in {"one", "paper", "laws"} and spec.name == "pdf":
            from rag.parsers.page_selection import selected_ranges
            from rag.parsers.errors import FileTooLarge

            def selected_blocks():
                report.pages_total = 0
                text_bytes = 0
                for interval in selected_ranges(ctx.parser_config.get("pages"), page_range):
                    control.check()
                    part = ParseReport()
                    for block in spec.load().parse(source, part, page_range=interval, limits=limits, **options):
                        text_bytes += len(block.text.encode("utf-8"))
                        if text_bytes > limits.max_text_bytes:
                            raise FileTooLarge()
                        yield block
                    report.pages_total += int(part.pages_total or 0)
                    report.pages_without_text += part.pages_without_text
                    report.images_skipped += part.images_skipped
                    report.layout_regions += part.layout_regions
                    report.layout_backend = part.layout_backend or report.layout_backend
                    for note in part.notes:
                        report.add_note(note)
            blocks = selected_blocks()
        else:
            blocks = spec.load().parse(source, report, page_range=page_range, limits=limits, **options)
        for chunk in chunker(text_blocks(blocks), get_chunker_config(ctx.parser_id, ctx.parser_config)):
            control.check()
            if chunk.text.strip():
                chunks.append(chunk)
    return chunks


def _store_thumbnail(ctx: TaskContext, path: Path, settings: Settings | None = None) -> None:
    if ctx.doc_suffix.lower().lstrip(".") != "pdf" or ctx.from_page != 0 or task_service.has_thumbnail(ctx.doc_id):
        return
    try:
        task_service.store_thumbnail(ctx.doc_id, thumbnail_data_url(path, settings=settings))
    except Exception as exc:  # noqa: BLE001 - a missing thumbnail never fails the task
        logger.info("thumbnail skipped", extra={"task": ctx.task_id, "error_type": type(exc).__name__})


def _drop_task_chunks(ctx: TaskContext, deps: PipelineDeps, index: str) -> None:
    deps.doc_store.delete({"task_id": [ctx.task_id]}, index, ctx.dataset_id)


def _current_switch(ctx: TaskContext, deps: PipelineDeps, index: str) -> task_service.DocSwitch:
    """Fresh document state. A cancelled document stops and keeps its chunks; a replaced task, a deleted document or any other run state removes this task's chunks and stops."""
    switch = task_service.document_switch(ctx.doc_id)
    if switch is not None and switch.run == RUN_CANCELLED and task_service.task_is_current(ctx.task_id):
        raise TaskCancelled("document cancelled")  # a user cancel keeps the chunks indexed so far (D-06)
    if switch is None or switch.run != "1" or not task_service.task_is_current(ctx.task_id):
        with _step("index", ctx):
            _drop_task_chunks(ctx, deps, index)
        raise TaskCancelled("task replaced")
    return switch


def _embed_batch(ctx: TaskContext, deps: PipelineDeps, control: TaskControl, chunks: list[Chunk], dimension: int) -> list[list[float]]:
    vectors = deps.embedder.encode([c.text for c in chunks], ctx, control, dimension)
    if len(vectors) != len(chunks) or any(len(v) != dimension for v in vectors):
        raise TaskFailure("embed", "dimension_mismatch")
    return [l2_normalize(v) for v in vectors]


def _index_batches(ctx: TaskContext, deps: PipelineDeps, control: TaskControl, chunks: list[Chunk], dimension: int, index: str) -> list[str]:
    ids: list[str] = []
    size = deps.settings.ingest.batch_size
    total = len(chunks)
    for start in range(0, total, size):
        control.check()
        switch = _current_switch(ctx, deps, index)
        batch = chunks[start : start + size]
        with _step("embed", ctx):
            vectors = _embed_batch(ctx, deps, control, batch, dimension)
        control.check()
        with _step("index", ctx):
            rows = [
                build_row(
                    c,
                    index=start + k,
                    doc_id=ctx.doc_id,
                    kb_id=ctx.dataset_id,
                    doc_name=ctx.doc_name,
                    task_id=ctx.task_id,
                    from_page=ctx.from_page,
                    to_page=ctx.to_page,
                    vector=v,
                    enabled=switch.enabled,
                )
                for k, (c, v) in enumerate(zip(batch, vectors, strict=True))
            ]
            if deps.doc_store.insert(rows, index, ctx.dataset_id):
                raise TaskFailure("index", "index_unavailable")
            ids.extend(r["id"] for r in rows)
            if not task_service.task_is_current(ctx.task_id):
                _drop_task_chunks(ctx, deps, index)
                raise TaskCancelled("task replaced")
            done = start + len(batch)
            task_service.set_progress(ctx.task_id, PARSED_PROGRESS + (1 - PARSED_PROGRESS) * done / total, f"Indexed {done} of {total} chunks.")
    return ids


def _check_cap(ctx: TaskContext, count: int) -> None:
    if count:
        parsed_chunk_id(ctx.doc_id, ctx.from_page, count - 1, ctx.to_page)  # raises too_many_chunks before any embedding


def run_pipeline(ctx: TaskContext, control: TaskControl, deps: PipelineDeps) -> PipelineResult:
    """Run one task. Raises ``TaskCancelled``, ``LockLost`` or ``TaskFailure``; the caller marks the task done or failed."""
    with _step("fetch", ctx):
        if ctx.doc_run != "1" or not task_service.task_is_current(ctx.task_id):
            raise TaskCancelled("task not current")
    with _step("chunk", ctx):
        get_chunker(ctx.parser_id)
    with _step("embed", ctx):
        dimension = _embedding_dimension(ctx)
    index = index_name(ctx.tenant_id)
    with _step("index", ctx):
        deps.doc_store.create_idx(index, ctx.dataset_id, dimension, ctx.parser_id)
    report = ParseReport()
    release_database_connection()
    with tempfile.TemporaryDirectory(prefix="ingest-") as tmp:
        with _step("fetch", ctx):
            path = _fetch(ctx, deps, Path(tmp))
        control.check()
        with _step("parse", ctx):
            chunks = _parse_and_chunk(ctx, deps, control, path, report)
        _store_thumbnail(ctx, path, deps.settings)
    is_pdf = ctx.doc_suffix.lower().lstrip(".") == "pdf"
    if not chunks and not is_pdf:
        raise TaskFailure("chunk", "no_readable_text")
    with _step("chunk", ctx):
        _check_cap(ctx, len(chunks))
    with _step("index", ctx):
        deps.doc_store.delete({"doc_id": [ctx.doc_id], "task_id": [ctx.task_id]}, index, ctx.dataset_id)
    pages_total = int(report.pages_total or 0)
    if report.pages_without_text:
        task_service.set_progress(ctx.task_id, PARSED_PROGRESS, f"{report.pages_without_text} of {pages_total} pages in this range had no readable text.")
    ids = _index_batches(ctx, deps, control, chunks, dimension, index) if chunks else []
    deps.embedder.forget(ctx.task_id)
    # Single machine lines the roll-up reads back (the latest of each wins when a task is retried).
    task_service.set_progress(ctx.task_id, 1.0, f"[pages] total={pages_total} without_text={report.pages_without_text}")
    task_service.set_progress(ctx.task_id, 1.0, f"[skipped] images={report.images_skipped}")
    if report.layout_backend:
        task_service.set_progress(ctx.task_id, 1.0, f"[layout] backend={report.layout_backend} regions={report.layout_regions}")
    return PipelineResult(tuple(ids), len(ids), pages_total, report.pages_without_text, report.images_skipped)
