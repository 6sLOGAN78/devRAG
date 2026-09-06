from quart import Blueprint, jsonify

ml_bp = Blueprint('ml', __name__)

@ml_bp.route('/health', methods=['GET', 'OPTIONS'])
async def health():
    return jsonify({"status": "ok"})
