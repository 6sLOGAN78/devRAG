"""One place that turns any exception into a step, a code and a plain sentence (D-05, D-08, D-23, R-158).

The sentence is fixed per code (``PLAIN_MESSAGES``, the same copy the SPA shows). A message that could carry a path, a key or a trace is refused at
construction. The only free text is ``detail`` (the already sanitized provider refusal), redacted and cut to 300 characters.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from api.db.services.service_errors import ServiceError
from api.utils import reasons
from common.doc_store.doc_store_base import DimensionConflict, DocStoreError
from common.ingest_codes import PLAIN_MESSAGES, is_terminal
from common.log_utils import redact_text
from rag.chunking.factory import ChunkerUnavailable
from rag.chunking.errors import ChunkTooLong
from rag.parsers.errors import ParserError
from rag.utils.storage_base import StorageError

MAX_DETAIL = 300
UNEXPECTED = "unexpected"

_UNSAFE = re.compile(r"/|\\|[A-Za-z]:|Traceback|File \"")
_LINE = re.compile(r"\[failed\] step=(\w+) code=(\w+) message=(.*?)(?: detail=(.*))?$")


@dataclass(frozen=True)
class FailureInfo:
    step: str
    code: str
    message: str
    detail: str = ""


def _guard(message: str) -> str:
    if _UNSAFE.search(message):
        raise ValueError("failure message must not contain a path or trace")
    return message


def _clean_detail(detail: str) -> str:
    text = redact_text(" ".join(detail.split()))[:MAX_DETAIL]
    return "" if _UNSAFE.search(text) else text


class TaskFailure(Exception):
    def __init__(self, step: str, code: str, message: str | None = None, *, detail: str = "") -> None:
        self.step = step
        self.code = code
        self.message = _guard(message if message is not None else PLAIN_MESSAGES.get(code, PLAIN_MESSAGES[UNEXPECTED]))
        self.detail = _clean_detail(detail) if detail else ""
        super().__init__(code)

    def __str__(self) -> str:
        return self.code

    @property
    def terminal(self) -> bool:
        return is_terminal(self.code)

    @property
    def info(self) -> FailureInfo:
        return FailureInfo(self.step, self.code, self.message, self.detail)

    def line(self) -> str:
        return format_failure_line(self.step, self.code, self.message, self.detail)


def format_failure_line(step: str, code: str, message: str, detail: str = "") -> str:
    line = f"[failed] step={step} code={code} message={_guard(message)}"
    return f"{line} detail={_clean_detail(detail)}" if detail and _clean_detail(detail) else line


def parse_failure_line(progress_msg: str | None) -> FailureInfo | None:
    for raw in reversed((progress_msg or "").splitlines()):
        found = _LINE.search(raw.strip())
        if found:
            return FailureInfo(found.group(1), found.group(2), found.group(3), found.group(4) or "")
    return None


_SERVICE_CODES = {
    reasons.PROVIDER_TIMEOUT: reasons.PROVIDER_TIMEOUT,
    reasons.PROVIDER_RATE_LIMITED: reasons.PROVIDER_RATE_LIMITED,
    reasons.PROVIDER_UNREACHABLE: reasons.PROVIDER_UNREACHABLE,
    reasons.PROVIDER_REFUSED: reasons.PROVIDER_REFUSED,
    reasons.MODEL_UNAVAILABLE: reasons.MODEL_UNAVAILABLE,
    reasons.DIMENSION_MISMATCH: reasons.DIMENSION_MISMATCH,
}


def classify(exc: BaseException, step: str) -> TaskFailure:
    """Map ``exc`` once. The text of provider, storage and parser exceptions is never copied (only a refusal's sanitized message)."""
    if isinstance(exc, TaskFailure):
        return exc
    if isinstance(exc, ParserError):
        return TaskFailure("parse", exc.code)
    if isinstance(exc, ChunkTooLong):
        return TaskFailure("chunk", "chunk_too_long")
    if isinstance(exc, ChunkerUnavailable):
        return TaskFailure("chunk", "chunker_unavailable")
    if isinstance(exc, ServiceError):
        code = _SERVICE_CODES.get(exc.reason)
        if code == reasons.PROVIDER_REFUSED:
            return TaskFailure("embed", code, detail=exc.message)
        return TaskFailure("embed", code or UNEXPECTED)
    if isinstance(exc, StorageError):
        return TaskFailure("fetch", "storage_unavailable")
    if isinstance(exc, DimensionConflict):
        return TaskFailure("index", "dimension_mismatch")
    if isinstance(exc, DocStoreError):
        return TaskFailure("index", "index_unavailable")
    return TaskFailure(step, UNEXPECTED)
