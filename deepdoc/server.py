"""Authenticated byte-only entry to isolated native processing."""

from __future__ import annotations

import asyncio
import hmac
import json
import math
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Protocol

from quart import Quart, jsonify, request
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from deepdoc.model_runtime import NativeError


class OCRRuntime(Protocol):
    def ocr(self, content: bytes) -> dict[str, Any]: ...


from deepdoc.ocr_result import validate_result


def create_app(runtime: OCRRuntime, token: str, *, max_bytes: int = 100 * 1024 * 1024, deadline: float = 60.0, max_result_bytes: int = 32 * 1024 * 1024) -> Quart:
    if len(token) < 24:
        raise ValueError("an operator token is required")
    app = Quart(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = max_bytes + 64 * 1024
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="deepdoc-native")
    inflight: asyncio.Future | None = None

    @app.after_serving
    async def close_executor():
        executor.shutdown(wait=False, cancel_futures=True)

    @app.before_request
    async def authenticate():
        if request.path != "/health":
            supplied = request.headers.get("Authorization", "")
            if not hmac.compare_digest(supplied.encode(), f"Bearer {token}".encode()):
                return jsonify(error="unauthorized", schema_version=1), 401
        return None

    @app.get("/health")
    async def health():
        return jsonify(schema_version=1, status="ready", capabilities=getattr(runtime, "capabilities", ["ocr"]))

    @app.errorhandler(RequestEntityTooLarge)
    async def oversized(_error):
        return jsonify(schema_version=1, error="input_too_large"), 413

    @app.errorhandler(BadRequest)
    async def malformed(_error):
        return jsonify(schema_version=1, error="invalid_request"), 400

    async def execute(operation: str):
        nonlocal inflight
        if inflight is not None and not inflight.done():
            return jsonify(schema_version=1, error="busy"), 503
        if request.mimetype != "multipart/form-data":
            return jsonify(schema_version=1, error="invalid_request"), 400
        files, form = await request.files, await request.form
        allowed_form = set() if operation in {"ocr", "layout", "normalize-image", "tsr"} else {"options"}
        if set(files) != {"file"} or len(files.getlist("file")) != 1 or set(form) - allowed_form or request.args or len(form.getlist("options")) > 1:
            return jsonify(schema_version=1, error="invalid_request"), 400
        content = files["file"].read(max_bytes + 1)
        if len(content) > max_bytes:
            return jsonify(schema_version=1, error="input_too_large"), 413
        if not content:
            return jsonify(schema_version=1, error="invalid_image"), 400
        if inflight is not None and not inflight.done():
            return jsonify(schema_version=1, error="busy"), 503
        if operation == "ocr":
            call, args = runtime.ocr, (content,)
        elif operation in {"layout", "normalize-image", "tsr"}:
            handler = {"layout": "layout_image", "normalize-image": "normalize_image", "tsr": "table_image"}[operation]
            call = getattr(runtime, handler, None)
            if call is None:
                return jsonify(schema_version=1, error="capability_unavailable"), 503
            args = (content,)
        else:
            try:
                encoded = form.get("options", "{}")
                if len(encoded) > 4096:
                    raise ValueError
                options = json.loads(encoded)
                if not isinstance(options, dict):
                    raise ValueError
            except (ValueError, RecursionError):
                return jsonify(schema_version=1, error="invalid_options"), 400
            if operation == "asr":
                if set(options) - {"language", "probe"}:
                    return jsonify(schema_version=1, error="invalid_options"), 400
                call = getattr(runtime, "process_asr", None)
            else:
                call = getattr(runtime, "process_pdf", None)
            if call is None:
                return jsonify(schema_version=1, error="capability_unavailable"), 503
            args = (content, options) if operation == "asr" else (operation, content, options)
        inflight = asyncio.get_running_loop().run_in_executor(executor, call, *args)
        # Retrieving exceptions prevents unhandled-future logs if the client goes away.
        inflight.add_done_callback(lambda future: future.exception() if not future.cancelled() else None)
        try:
            result = await asyncio.wait_for(asyncio.shield(inflight), timeout=deadline)
            if operation == "ocr":
                validate_result(result)
            elif operation == "asr" and not options.get("probe"):
                from rag.parsers.audio_segments import transcript_of
                try:
                    transcript_of(result)
                except ValueError:
                    raise NativeError("invalid_native_result", 502) from None
            elif isinstance(result, bytes):
                if operation != "page-image" or len(result) > max_result_bytes:
                    raise NativeError("output_too_large", 413)
                return app.response_class(result, mimetype="image/jpeg")
            payload = json.dumps(result, ensure_ascii=False, allow_nan=False)
            if len(payload.encode()) > max_result_bytes:
                raise NativeError("output_too_large", 413)
            return app.response_class(payload, mimetype="application/json")
        except TimeoutError:
            # The uncancellable native thread keeps the slot until it actually finishes.
            return jsonify(schema_version=1, error="native_timeout"), 504
        except NativeError as exc:
            return jsonify(schema_version=1, error=exc.code), exc.status
        except Exception:
            return jsonify(schema_version=1, error="native_failure"), 500

    @app.post("/v1/ocr")
    async def ocr():
        return await execute("ocr")

    @app.post("/v1/asr")
    async def asr():
        return await execute("asr")

    @app.post("/v1/parse")
    async def parse_pdf():
        return await execute("parse")

    @app.post("/v1/layout")
    async def layout():
        return await execute("layout")

    @app.post("/v1/tsr")
    async def tables():
        return await execute("tsr")

    @app.post("/v1/images/normalize")
    async def normalize_image():
        return await execute("normalize-image")

    @app.post("/v1/document/info")
    async def document_info():
        return await execute("info")

    @app.post("/v1/page-image")
    async def page_image():
        return await execute("page-image")

    return app


async def main() -> None:
    from hypercorn.asyncio import serve
    from hypercorn.config import Config

    from deepdoc.model_runtime import ModelRuntime
    from deepdoc.native_runtime import NativeRuntime

    token = os.environ.get("DEEPDOC_API_TOKEN", "")
    if len(token) < 24:
        raise ValueError("an operator token is required")
    runtime = ModelRuntime(Path(os.environ.get("DEEPDOC_MODEL_DIR", "/models")))
    app = create_app(NativeRuntime(runtime), token)
    config = Config()
    config.bind = ["0.0.0.0:9390"]
    config.workers = 1
    config.accesslog = None
    config.errorlog = "-"
    await serve(app, config)


if __name__ == "__main__":
    asyncio.run(main())
