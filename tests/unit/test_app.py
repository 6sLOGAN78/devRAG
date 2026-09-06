import pytest
from api.apps import create_app

@pytest.mark.asyncio
async def test_app_creation():
    app = create_app()
    assert app is not None
    assert app.name == 'api.apps'
