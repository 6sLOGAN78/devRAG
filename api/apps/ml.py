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
