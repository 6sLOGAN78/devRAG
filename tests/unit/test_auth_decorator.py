import pytest
from quart import Quart, jsonify, g
from api.apps.auth_decorator import require_auth
from api.db.db_models import UserTenant
import jwt
from unittest.mock import patch, MagicMock

app = Quart(__name__)

@app.route('/protected')
@require_auth
async def protected():
    return jsonify({"user_id": g.user_id, "tenant_id": g.tenant_id, "role": g.role})

@pytest.mark.asyncio
async def test_auth_no_token():
    client = app.test_client()
    response = await client.get('/protected')
    assert response.status_code == 401

@pytest.mark.asyncio
@patch('api.apps.auth_decorator.redis_client')
@patch('api.apps.auth_decorator.UserTenant')
async def test_auth_valid(mock_ut, mock_redis):
    # Mock redis session
    import json
    mock_redis.get.return_value = json.dumps({"session_id": "sess-123"})
    
    # Mock UserTenant
    mock_tenant = MagicMock()
    mock_tenant.tenant_id = "tenant-123"
    mock_tenant.role = "owner"
    mock_select = MagicMock()
    mock_select.where.return_value = [mock_tenant]
    mock_ut.select.return_value = mock_select
    
    from api.apps.auth_decorator import cfg
    token = jwt.encode({"user_id": "user-123", "session_id": "sess-123"}, cfg.auth.jwt_secret, algorithm="HS256")
    
    client = app.test_client()
    response = await client.get('/protected', headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = await response.get_json()
    assert data["user_id"] == "user-123"
    assert data["tenant_id"] == "tenant-123"
    assert data["role"] == "owner"

@pytest.mark.asyncio
@patch('api.apps.auth_decorator.redis_client')
@patch('api.apps.auth_decorator.UserTenant')
async def test_auth_invalid_tenant(mock_ut, mock_redis):
    import json
    mock_redis.get.return_value = json.dumps({"session_id": "sess-123"})
    
    mock_tenant = MagicMock()
    mock_tenant.tenant_id = "tenant-123"
    mock_tenant.role = "owner"
    mock_select = MagicMock()
    mock_select.where.return_value = [mock_tenant]
    mock_ut.select.return_value = mock_select
    
    from api.apps.auth_decorator import cfg
    token = jwt.encode({"user_id": "user-123", "session_id": "sess-123"}, cfg.auth.jwt_secret, algorithm="HS256")
    
    client = app.test_client()
    response = await client.get('/protected', headers={
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": "tenant-999"
    })
    assert response.status_code == 403

@pytest.mark.asyncio
@patch('api.apps.auth_decorator.redis_client')
@patch('api.apps.auth_decorator.UserTenant')
async def test_auth_invite_blocked(mock_ut, mock_redis):
    import json
    mock_redis.get.return_value = json.dumps({"session_id": "sess-123"})
    
    mock_tenant = MagicMock()
    mock_tenant.tenant_id = "tenant-123"
    mock_tenant.role = "invite"
    mock_select = MagicMock()
    mock_select.where.return_value = [mock_tenant]
    mock_ut.select.return_value = mock_select
    
    from api.apps.auth_decorator import cfg
    token = jwt.encode({"user_id": "user-123", "session_id": "sess-123"}, cfg.auth.jwt_secret, algorithm="HS256")
    
    client = app.test_client()
    response = await client.get('/protected', headers={
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": "tenant-123"
    })
    assert response.status_code == 403
