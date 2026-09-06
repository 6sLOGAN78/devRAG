import sys
import os
import logging
import traceback
from quart import Quart, jsonify
from quart_cors import cors

# Adjust python path to find common
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from common.settings import load_config  # noqa: F401, E402
from api.apps.ml import ml_bp
from api.apps.agents import agents_bp
from api.apps.chat_handler import chat_bp


from api.utils.logger import setup_logger
setup_logger()
logger = logging.getLogger(__name__)

def create_app():
    app = Quart(__name__)

    # Setup CORS
    app = cors(app, allow_origin="*")

    @app.before_serving
    async def startup():
        import asyncio
        from api.services.executor_cleaner import clean_task_executor_loop
        asyncio.create_task(clean_task_executor_loop())

    @app.before_request
    async def setup_request_context():
        import uuid
        from quart import request, g
        g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        logger.info(f"Request: {request.method} {request.path}")
    @app.errorhandler(Exception)
    async def handle_exception(e):
        from quart import g
        # Do not expose internal stack traces in production responses.
        logger.error(f"Unhandled Exception: {traceback.format_exc()}", extra={"event": "internal_error"})
        return jsonify({"error": {"code": "INTERNAL_ERROR", "message": "Internal Server Error", "request_id": getattr(g, "request_id", "")}}), 500

    @app.errorhandler(404)
    async def not_found(e):
        from quart import g
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Not Found", "request_id": getattr(g, "request_id", "")}}), 404
    # Register blueprints
    app.register_blueprint(ml_bp, url_prefix='/api/v1/ml')
    app.register_blueprint(agents_bp, url_prefix='/api/v1/agents')
    app.register_blueprint(chat_bp, url_prefix='/api/v1/chat')


    return app
