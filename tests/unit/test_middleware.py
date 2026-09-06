import pytest
from api.apps import create_app

@pytest.fixture
def app():
    return create_app()

@pytest.mark.asyncio
async def test_cors_headers(app):
    client = app.test_client()
    response = await client.options('/api/v1/ml/health', headers={'Origin': 'http://localhost'})
    assert 'Access-Control-Allow-Origin' in response.headers
    assert response.headers['Access-Control-Allow-Origin'] == '*'

@pytest.mark.asyncio
async def test_error_handling(app):
    @app.route('/error')
    async def error():
        raise ValueError("Test Error")

    client = app.test_client()
    response = await client.get('/error')
    assert response.status_code == 500
    data = await response.get_json()
    assert 'error' in data
