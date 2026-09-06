import pytest
from api.apps import create_app

@pytest.fixture
def app():
    return create_app()

@pytest.mark.asyncio
async def test_agents_blueprint_registered(app):
    assert 'agents' in app.blueprints
