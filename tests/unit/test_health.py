import pytest
from api.apps import create_app

@pytest.fixture
def app():
    return create_app()

@pytest.mark.asyncio
async def test_health_json(app):
    client = app.test_client()
    response = await client.get('/api/v1/ml/health')
    assert response.status_code == 200
    data = await response.get_json()
    assert data == {"status": "ok"}
