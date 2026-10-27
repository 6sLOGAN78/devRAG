"""Authenticated normalized-image bytes; original-source visibility is checked on every read."""

from quart import Blueprint, Response, current_app, g

from api.apps.service_errors import service_error_response
from api.db.services import document_asset_service
from api.db.services.service_errors import ServiceError
from api.utils.blocking import STORAGE_EXECUTOR, run_blocking

asset_bp = Blueprint("document_asset", __name__)


@asset_bp.get("/api/v1/documents/images/<image_id>")
async def image(image_id: str) -> Response:
    settings, principal = current_app.extensions["ragflow_settings"], g.principal
    try:
        data = await run_blocking(STORAGE_EXECUTOR, lambda: document_asset_service.read_asset(settings, principal, image_id), timeout=30)
        return Response(
            data,
            mimetype="image/png",
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "sandbox",
                "Content-Length": str(len(data)),
            },
        )
    except ServiceError as exc:
        return service_error_response(exc)
