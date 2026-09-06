import pytest
from peewee import SqliteDatabase
from api.db.db_models import DocumentTask, DocumentChunk

test_db = SqliteDatabase(':memory:')

@pytest.fixture(autouse=True)
def setup_db():
    test_db.bind([DocumentTask, DocumentChunk], bind_refs=False, bind_backrefs=False)
    test_db.connect()
    test_db.create_tables([DocumentTask, DocumentChunk])
    yield
    test_db.drop_tables([DocumentTask, DocumentChunk])
    test_db.close()

def test_document_task_creation():
    task = DocumentTask.create(
        id="task-123",
        document_id="doc-123",
        tenant_id="tenant-123",
        status="running",
        progress=50
    )
    assert task.id == "task-123"
    assert task.document_id == "doc-123"
    assert task.tenant_id == "tenant-123"
    assert task.status == "running"
    assert task.progress == 50
    assert task.error_msg is None

def test_document_chunk_creation():
    chunk = DocumentChunk.create(
        id="chunk-123",
        document_id="doc-123",
        tenant_id="tenant-123",
        content="This is a chunk of text.",
        chunk_index=0,
        content_type="text",
        page_numbers="[1]",
        source_regions="[{\"page\": 1, \"bbox\": [0, 0, 100, 100]}]",
        source_block_ids="[\"block-1\"]",
        token_count=10
    )
    assert chunk.id == "chunk-123"
    assert chunk.content == "This is a chunk of text."
    assert chunk.chunk_index == 0
    assert chunk.token_count == 10
