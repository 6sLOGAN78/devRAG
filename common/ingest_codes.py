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
    "file_too_large",
    "archive_limits_exceeded",
    "too_many_chunks",
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
        "provider_refused",
        "dimension_mismatch",
        "model_unavailable",
        "document_deleted",
    }
)

# Chunking methods in documentation order (UI-SPEC chunking-method dialog).
METHOD_ORDER: tuple[str, ...] = ("naive", "qa", "paper", "book", "laws", "presentation", "table", "manual")
IMPLEMENTED_PARSERS: frozenset[str] = frozenset({"naive"})


def is_terminal(code: str) -> bool:
    return code in TERMINAL_CODES
