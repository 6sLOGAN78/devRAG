"""Page image and original-file routes (plan 04-20; DOC-21, PARSE-03, UI-16, UI-19, T-04-20-01..07).

* ``GET /api/v1/datasets/<dataset_id>/documents/<doc_id>/pages/<n>/image`` answers a JPEG of page ``n`` (1-based) of a PDF at zoom 3 with a content-hash
  ``ETag`` (``If-None-Match`` is answered with 304 and no body) and ``Cache-Control: private``. A page beyond the last, a malformed page number, a
  document that is not a PDF and anything not visible are the one 404. A damaged PDF is 400 ``preview_unavailable``.
* ``GET /api/v1/datasets/<dataset_id>/documents/<doc_id>/content`` streams the original bytes. PDF, PNG and JPEG are inline; every other type is an
  attachment and HTML is never ``text/html``. ``nosniff`` and ``Content-Security-Policy: sandbox`` are always set.
* ``GET .../content?format=text`` answers ``{text, cut}`` for text-like files only (400 ``preview_unavailable`` otherwise).

Both routes need only dataset visibility. The SPA sends the Authorization header; no route reads a token from the URL. Rendering runs in the PDF
executor with a 30 s deadline; the stream is pulled in chunks through the storage executor and always closed.
"""

from __future__ import annotations

import re
import threading
from collections.abc import AsyncIterator
from urllib.parse import quote

from quart import Blueprint, Response, current_app, g, request

from api.apps.service_errors import service_error_response
from api.db.services import knowledgebase_service as datasets
from api.db.services import page_service
from api.db.services.service_errors import Kind, ServiceError
from api.utils import reasons
from api.utils.api_utils import json_result
from api.utils.blocking import DB_EXECUTOR, PDF_EXECUTOR, STORAGE_EXECUTOR, run_blocking
from common.settings import Settings

page_bp = Blueprint("page", __name__)

# Identical to the endpoint rows in conf/routes.yaml (Quart spells a path parameter <name>, the registry {name}).
IMAGE = "/api/v1/datasets/<dataset_id>/documents/<doc_id>/pages/<n>/image"
CONTENT = "/api/v1/datasets/<dataset_id>/documents/<doc_id>/content"

DB_TIMEOUT_SECONDS = 10.0
RENDER_TIMEOUT_SECONDS = 30.0
CHUNK_TIMEOUT_SECONDS = 30.0
TEXT_TIMEOUT_SECONDS = 30.0
IMAGE_MAX_AGE = 3600
_PAGE_NUMBER = re.compile(r"[0-9]{1,9}")
_SAFE_HEADERS = {"X-Content-Type-Options": "nosniff"}


def _settings() -> Settings:
    return current_app.extensions["ragflow_settings"]


def _not_found() -> ServiceError:
    return ServiceError(Kind.NOT_FOUND, reasons.DATASET_NOT_FOUND, "not found")


def _etag_matches(header: str | None, etag: str) -> bool:
    if not header:
        return False
    wanted = etag.removeprefix("W/")
    return any(part.strip().removeprefix("W/") in (wanted, "*") for part in header.split(","))


async def page_image(dataset_id: str, doc_id: str, n: str) -> Response:
    try:
        settings = _settings()
        principal = g.principal
        if _PAGE_NUMBER.fullmatch(n) is None or int(n) < 1:
            raise _not_found()
        number = int(n)
        visible = await run_blocking(DB_EXECUTOR, datasets.load_visible_dataset, principal, dataset_id, timeout=DB_TIMEOUT_SECONDS)
        cache = {"Cache-Control": f"private, max-age={IMAGE_MAX_AGE}", **_SAFE_HEADERS}
        if request.headers.get("If-None-Match"):
            known = await run_blocking(PDF_EXECUTOR, lambda: page_service.page_etag(settings, visible, doc_id, number), timeout=RENDER_TIMEOUT_SECONDS)
            if known is not None and _etag_matches(request.headers.get("If-None-Match"), known):
                return Response(b"", status=304, headers={"ETag": known, **cache})
        rendered = await run_blocking(PDF_EXECUTOR, lambda: page_service.page_image(settings, visible, doc_id, number), timeout=RENDER_TIMEOUT_SECONDS)
        return Response(rendered.data, mimetype="image/jpeg", headers={"ETag": rendered.etag, **cache})
    except ServiceError as exc:
        return service_error_response(exc)


class _Pump:
    """Serialises ``next`` and ``close`` of one storage generator: a generator that is running in a worker thread cannot be closed from another."""

    def __init__(self, stream: page_service.ContentStream) -> None:
        self.stream = stream
        self._lock = threading.Lock()

    def next_chunk(self) -> bytes | None:
        with self._lock:
            return next(self.stream.chunks, None)

    def close(self) -> None:
        with self._lock:
            self.stream.close()


async def _body(pump: _Pump) -> AsyncIterator[bytes]:
    try:
        while True:
            chunk = await run_blocking(STORAGE_EXECUTOR, pump.next_chunk, timeout=CHUNK_TIMEOUT_SECONDS)
            if chunk is None:
                break
            yield chunk
    finally:  # also when the client leaves: cancellation cannot interrupt a submit, and the lock waits for a read in flight
        STORAGE_EXECUTOR.submit(pump.close)


def _disposition(inline: bool, filename: str) -> str:
    ascii_name = filename.encode("ascii", "replace").decode("ascii").replace("?", "_")
    return f"{'inline' if inline else 'attachment'}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"


async def content(dataset_id: str, doc_id: str) -> Response:
    try:
        settings = _settings()
        principal = g.principal
        wanted = request.args.get("format")
        if wanted not in (None, "text"):
            raise ServiceError(Kind.INVALID, reasons.QUERY_INVALID, "format must be text")
        visible = await run_blocking(DB_EXECUTOR, datasets.load_visible_dataset, principal, dataset_id, timeout=DB_TIMEOUT_SECONDS)
        if wanted == "text":
            preview = await run_blocking(STORAGE_EXECUTOR, lambda: page_service.content_text(settings, visible, doc_id), timeout=TEXT_TIMEOUT_SECONDS)
            return json_result(preview)
        stream = await run_blocking(STORAGE_EXECUTOR, lambda: page_service.content_stream(settings, visible, doc_id), timeout=DB_TIMEOUT_SECONDS)
        headers = {
            "Content-Disposition": _disposition(stream.inline, stream.filename),
            "Content-Security-Policy": "sandbox",
            "Cache-Control": "private, no-cache",
            **_SAFE_HEADERS,
        }
        if stream.size is not None:
            headers["Content-Length"] = str(stream.size)
        return Response(_body(_Pump(stream)), mimetype=stream.content_type, headers=headers)
    except ServiceError as exc:
        return service_error_response(exc)


page_bp.add_url_rule(IMAGE, endpoint="page_image", view_func=page_image, methods=["GET"])
page_bp.add_url_rule(CONTENT, endpoint="content", view_func=content, methods=["GET"])
