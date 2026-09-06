from quart import Blueprint, jsonify, g
from .auth_decorator import require_auth

ml_bp = Blueprint('ml', __name__)

@ml_bp.route('/health', methods=['GET', 'OPTIONS'])
async def health():
    return jsonify({"status": "ok"})

@ml_bp.route('/protected_info', methods=['GET'])
@require_auth
async def protected_info():
    return jsonify({
        "user_id": g.user_id,
        "tenant_id": g.tenant_id
    })

from quart import request
from api.services.parsing_service import parsing_service

@ml_bp.route('/parse_document', methods=['POST'])
async def parse_document():
    data = await request.get_json()
    if not data or 'task_id' not in data or 'document_id' not in data:
        return jsonify({"error": "Missing task_id or document_id"}), 400
    
    # Execute synchronously since it's dispatched by the Go worker and we expect to return 200 upon acceptance.
    # Wait, the Go Syncer expects to return 200 immediately, and the task executes in background?
    # Or does it block? The Go syncer runs `s.httpClient.Do(req)` and waits for response.
    # If parsing takes 2 minutes, Go Syncer blocks that goroutine (which is fine, it uses semaphore for bounded concurrency).
    # BUT, the HTTP client timeout in Go syncer is `10 * time.Second`.
    # Therefore, we MUST execute the parsing asynchronously, and return 200 immediately (Task Accepted).

    import asyncio
    asyncio.create_task(run_parsing_background(data['task_id'], data['document_id']))
    
    return jsonify({"status": "accepted", "task_id": data['task_id']}), 200

async def run_parsing_background(task_id: str, document_id: str):
    import asyncio
    # Run CPU/IO bound parsing in a separate thread to avoid blocking Quart event loop
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, parsing_service.process_task, task_id, document_id)
