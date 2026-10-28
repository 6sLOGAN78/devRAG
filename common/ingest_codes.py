"""The worker vocabulary: document run codes, step names, failure codes, terminal set and chunking-method ids.

This is the one place these are spelled (D-15, R-158). Pure constants; imports nothing from ``api`` or ``rag``.
"""

from __future__ import annotations

RUN_NOT_STARTED = "0"
RUN_RUNNING = "1"
RUN_CANCELLED = "2"
RUN_DONE = "3"
RUN_FAILED = "4"

# Status of a pipeline_operation_log row (plan 04-10).
LOG_RUNNING = "running"
LOG_DONE = "done"
LOG_FAILED = "failed"
LOG_CANCELLED = "cancelled"

STEPS: tuple[str, ...] = ("queue", "fetch", "parse", "chunk", "embed", "index")

FAILURE_CODES: tuple[str, ...] = (
    "no_readable_text",
    "unsupported_type",
    "chunker_unavailable",
    "file_damaged",
    "native_unavailable",
    "file_too_large",
    "archive_limits_exceeded",
    "too_many_chunks",
    "chunk_too_long",
    "provider_timeout",
    "provider_rate_limited",
    "provider_unreachable",
    "provider_refused",
    "model_unavailable",
    "dimension_mismatch",
    "index_unavailable",
    "storage_unavailable",
    "worker_lost",
    "queue_unavailable",
    "document_deleted",
    "unexpected",
)

# R-158 (plus too_many_chunks, R-155): fail at once, no retry. Everything else retries up to the attempt cap.
TERMINAL_CODES: frozenset[str] = frozenset(
    {
        "no_readable_text",
        "unsupported_type",
        "chunker_unavailable",
        "file_too_large",
        "archive_limits_exceeded",
        "too_many_chunks",
        "chunk_too_long",
        "provider_refused",
        "dimension_mismatch",
        "model_unavailable",
        "document_deleted",
    }
)

# Plain sentences per failure code: what the worker stores and the SPA shows (UI-SPEC "Failure reasons", D-08, D-23).
PLAIN_MESSAGES: dict[str, str] = {
    "no_readable_text": "This PDF has no readable text.",
    "unsupported_type": "Parsing isn't available yet for this file type.",
    "chunker_unavailable": "The chosen chunking method isn't available yet.",
    "file_damaged": "The file is damaged or incomplete and couldn't be opened.",
    "native_unavailable": "The native parsing service is not available. Try again shortly.",
    "file_too_large": "The file is too large to parse.",
    "archive_limits_exceeded": "The file unpacks to more data than is allowed, so it wasn't opened.",
    "too_many_chunks": "This document produced more chunks than one parsing task can store.",
    "chunk_too_long": "The whole document exceeds the embedding model context. Choose another chunking method.",
    "provider_timeout": "The embedding provider timed out.",
    "provider_rate_limited": "The embedding provider is limiting requests.",
    "provider_unreachable": "The embedding provider couldn't be reached.",
    "provider_refused": "The embedding provider refused the request.",
    "model_unavailable": "This dataset's embedding model is no longer available in the workspace.",
    "dimension_mismatch": "The embedding model returned vectors of a different size than this dataset uses.",
    "index_unavailable": "The search index wasn't available.",
    "storage_unavailable": "The stored file couldn't be read.",
    "worker_lost": "The worker stopped while parsing this document.",
    "queue_unavailable": "The task queue wasn't available.",
    "document_deleted": "The document was deleted while it was being parsed.",
    "unexpected": "Parsing failed for an unexpected reason.",
}

# Chunking methods in documentation order (UI-SPEC chunking-method dialog).
METHOD_ORDER: tuple[str, ...] = ("naive", "qa", "paper", "book", "laws", "presentation", "table", "manual", "resume", "picture", "email", "tag", "one", "audio")
IMPLEMENTED_PARSERS: frozenset[str] = frozenset({"naive", "one", "manual"})


def is_terminal(code: str) -> bool:
    return code in TERMINAL_CODES
