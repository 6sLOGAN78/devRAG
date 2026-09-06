import pytest
import json
import uuid
import asyncio
from unittest.mock import patch, AsyncMock
from quart import Quart
from api.apps import create_app
from peewee import SqliteDatabase
from api.db.db_models import ChatSession, ChatMessage, AgentCanvas, UserTenant, db
import jwt

test_db = SqliteDatabase(':memory:')

# Bind models to test_db for tests
@pytest.fixture(autouse=True)
def setup_database():
    with test_db.bind_ctx([ChatSession, ChatMessage, AgentCanvas, UserTenant]):
        test_db.create_tables([ChatSession, ChatMessage, AgentCanvas, UserTenant], safe=True)
        yield
        test_db.drop_tables([ChatSession, ChatMessage, AgentCanvas, UserTenant], safe=True)

@pytest.fixture
def auth_headers():
    token = jwt.encode({"user_id": "test_user", "session_id": "test_session"}, "secret", algorithm="HS256")
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": "test_tenant"
    }

@pytest.mark.asyncio
async def test_chat_completions_missing_session(test_client, auth_headers):
    # Mock redis session
    with patch("api.apps.auth_decorator.redis_client.get", new_callable=AsyncMock) as mock_redis:
        mock_redis.return_value = json.dumps({"session_id": "test_session"})
        UserTenant.create(user_id="test_user", tenant_id="test_tenant", role="admin")

        response = await test_client.post('/api/v1/chat/completions', json={
            "session_id": "missing_session",
            "message": "Hello"
        }, headers=auth_headers)
        
        assert response.status_code == 404
        data = await response.get_json()
        assert "not found" in data["error"]

@pytest.mark.asyncio
async def test_chat_completions_success(test_client, auth_headers):
    with patch("api.apps.auth_decorator.redis_client.get", new_callable=AsyncMock) as mock_redis:
        mock_redis.return_value = json.dumps({"session_id": "test_session"})
        UserTenant.create(user_id="test_user", tenant_id="test_tenant", role="admin")
        
        # Setup real graph
        graph_def = {
            "version": 1,
            "nodes": [
                {
                    "id": "mock_llm",
                    "type": "mock", # Assuming there's a mock node
                    "config": {"output": "Mock response"},
                    "inputs": {"query": "__start__.query"}
                }
            ],
            "edges": []
        }
        
        canvas = AgentCanvas.create(
            id=str(uuid.uuid4()),
            tenant_id="test_tenant",
            name="Test Canvas",
            graph_definition=json.dumps(graph_def),
            created_by="test_user"
        )
        
        session = ChatSession.create(
            id=str(uuid.uuid4()),
            user_id="test_user",
            tenant_id="test_tenant",
            agent_id=canvas.id,
            title="Test Session"
        )
        
        # Mock GraphRunner to emit tokens and succeed
        async def mock_run(self_obj, agent_graph, initial_inputs):
            callback = initial_inputs.get("__stream_callback__")
            if callback:
                callback("Mock ")
                callback("response")
            state = ExecutionState("test_exec")
            return ExecutionResult("success", state)

        with patch.object(GraphRunner, 'run', autospec=True) as mock_runner:
            mock_runner.side_effect = mock_run
            
            response = await test_client.post('/api/v1/chat/completions', json={
                "session_id": session.id,
                "message": "Hello"
            }, headers=auth_headers)
            
            assert response.status_code == 200
            
            async for chunk in response.response:
                data = chunk.decode("utf-8")
                assert "data: " in data
                
            # Verify database persistence
            messages = list(ChatMessage.select().where(ChatMessage.session_id == session.id).order_by(ChatMessage.created_at.asc()))
            assert len(messages) == 2
            assert messages[0].role == "user"
            assert messages[0].content == "Hello"
            assert messages[1].role == "assistant"
            assert messages[1].content == "Mock response"
