import pytest
from api.apps import create_app

@pytest.fixture
def app():
    return create_app()

@pytest.mark.asyncio
async def test_ml_blueprint_registered(app):
    assert 'ml' in app.blueprints
    client = app.test_client()
    response = await client.get('/api/v1/ml/health')
    assert response.status_code == 200
