import os
import sys
import json
import jwt
from functools import wraps
from quart import request, jsonify, g
import redis.asyncio as redis

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from common.settings import load_config
from api.db.db_models import UserTenant

cfg = load_config(os.environ.get('RAGFLOW_CONFIG', 'conf/service_conf.yaml'))

redis_client = redis.Redis(
    host=cfg.redis.host,
    port=cfg.redis.port,
    db=cfg.redis.db,
    decode_responses=True
)

def require_auth(f):
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401
            
        token = auth_header.split(' ')[1]
        try:
            claims = jwt.decode(token, cfg.auth.jwt_secret, algorithms=["HS256"])
        except Exception:
            return jsonify({"error": "Invalid or expired token"}), 401
            
        user_id = claims.get('user_id')
        session_id = claims.get('session_id')
        
        if not user_id or not session_id:
            return jsonify({"error": "Invalid token claims"}), 401
            
        session_data = await redis_client.get(f"session:{user_id}")
        if not session_data:
            return jsonify({"error": "Session inactive or expired"}), 401
            
        try:
            session_json = json.loads(session_data)
        except Exception:
            return jsonify({"error": "Invalid session data"}), 401
            
        if session_json.get('session_id') != session_id:
            return jsonify({"error": "Session mismatch"}), 401
            
        # Validate Tenant Context
        requested_tenant_id = request.headers.get('X-Tenant-ID')
        
        # Peewee is sync, so this blocks the loop briefly, but it's fine for MVP
        try:
            user_tenants = list(UserTenant.select().where(UserTenant.user_id == user_id))
        except Exception:
            return jsonify({"error": "Database error"}), 500
            
        if not user_tenants:
            return jsonify({"error": "Unauthorized tenant access"}), 403
            
        tenant_id = None
        role = None
        if requested_tenant_id:
            for ut in user_tenants:
                if ut.tenant_id == requested_tenant_id:
                    if ut.role == 'invite':
                        return jsonify({"error": "Unauthorized tenant access"}), 403
                    tenant_id = requested_tenant_id
                    role = ut.role
                    break
            if not tenant_id:
                return jsonify({"error": "Unauthorized tenant access"}), 403
        else:
            for ut in user_tenants:
                if ut.role != 'invite':
                    tenant_id = ut.tenant_id
                    role = ut.role
                    break
            if not tenant_id:
                return jsonify({"error": "Unauthorized tenant access"}), 403
            
        g.user_id = user_id
        g.tenant_id = tenant_id
        g.role = role
        
        return await f(*args, **kwargs)
        
    return decorated_function
