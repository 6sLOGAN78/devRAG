import pytest
import os
import tempfile
from unittest.mock import patch, MagicMock
from api.apps import create_app
from api.db.db_models import DocumentTask, Document, DocumentChunk
from peewee import SqliteDatabase

test_db_path = os.path.join(tempfile.gettempdir(), 'test_db.sqlite')
test_db = SqliteDatabase(test_db_path)

@pytest.fixture(autouse=True)
def setup_db():
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    test_db.bind([Document, DocumentTask, DocumentChunk], bind_refs=False, bind_backrefs=False)
    test_db.connect()
    test_db.create_tables([Document, DocumentTask, DocumentChunk])
    yield
    test_db.drop_tables([Document, DocumentTask, DocumentChunk])
    test_db.close()
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

@pytest.fixture
def app():
    app = create_app()
    app.config.update({"TESTING": True})
    return app

@pytest.fixture
def client(app):
    return app.test_client()

@patch('api.services.storage_service.storage_service.download_file')
@pytest.mark.asyncio
async def test_parse_document_api(mock_download, client):
    # Setup test data
    doc = Document.create(
        id="doc-123",
        dataset_id="ds-123",
        tenant_id="tenant-123",
        name="test.txt",
        size="100",
        type="txt",
        minio_path="ragflow/test.txt",
        created_by="user-123"
    )
    
    task = DocumentTask.create(
        id="task-123",
        document_id="doc-123",
        tenant_id="tenant-123",
        status="running",
        progress=0
    )

    # Mock download file to create a dummy txt file
    def mock_download_effect(bucket, object_name, temp_path):
        with open(temp_path, 'w') as f:
            f.write("This is a test paragraph.\n\nThis is another paragraph.")
    mock_download.side_effect = mock_download_effect

    # Call API
    response = await client.post('/api/v1/ml/parse_document', json={
        "task_id": "task-123",
        "document_id": "doc-123"
    })
    
    assert response.status_code == 200
    data = await response.get_json()
    assert data['status'] == 'accepted'

    # Need to wait for background task to complete.
    import asyncio
    await asyncio.sleep(0.5) # allow asyncio background task to run

    # Verify DB changes
    task_reloaded = DocumentTask.get_by_id("task-123")
    assert task_reloaded.status == 'success'
    assert task_reloaded.progress == 100

    doc_reloaded = Document.get_by_id("doc-123")
    assert doc_reloaded.parse_status == 'success'

    chunks = list(DocumentChunk.select().where(DocumentChunk.document_id == "doc-123"))
    assert len(chunks) == 1
    assert chunks[0].content == "This is a test paragraph.\n\nThis is another paragraph."
    
