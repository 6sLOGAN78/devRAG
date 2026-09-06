import pytest
from unittest.mock import MagicMock, patch
from rag.vector_store.base import VectorRecord, SearchResult
from rag.vector_store.infinity_adapter import InfinityAdapter
from rag.utils.ob_conn_base import DocumentStoreBase
from common.redis_conn import RedisDistributedLock

@pytest.fixture
def mock_infinity_client():
    with patch("infinity.connect") as mock_connect:
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_table = MagicMock()
        
        mock_connect.return_value = mock_client
        mock_client.get_database.return_value = mock_db
        mock_db.get_table.return_value = mock_table
        
        yield mock_connect, mock_client, mock_db, mock_table

def test_infinity_create_index(mock_infinity_client):
    mock_connect, mock_client, mock_db, mock_table = mock_infinity_client
    
    adapter = InfinityAdapter(db_name="test_db")
    adapter.create_index("test_index", 128)
    
    mock_client.create_database.assert_called_once()
    mock_db.create_table.assert_called_once()
    # The table is created and then create_index is called
    assert mock_db.create_table.return_value.create_index.call_count == 1

def test_infinity_bulk_insert(mock_infinity_client):
    mock_connect, mock_client, mock_db, mock_table = mock_infinity_client
    
    adapter = InfinityAdapter(db_name="test_db")
    records = [
        VectorRecord(id="1", document_id="doc1", dataset_id="ds1", content="hello", embedding=[0.1]*128)
    ]
    
    adapter.bulk_insert("test_index", records)
    mock_db.get_table.assert_called_with("test_index")
    mock_table.insert.assert_called_once()
    
    # Check that insert was called with the right data shape
    args = mock_table.insert.call_args[0][0]
    assert len(args) == 1
    assert args[0]["id"] == "1"
    assert args[0]["embedding"] == [0.1]*128

@patch("common.redis_conn.RedisDistributedLock.acquire")
@patch("common.redis_conn.RedisDistributedLock.release")
def test_document_store_lock(mock_release, mock_acquire):
    mock_acquire.return_value = True
    
    doc_store = DocumentStoreBase(kb_id="test_kb")
    doc_store.initialize()
    
    mock_acquire.assert_called()
    mock_release.assert_called()

@patch("common.redis_conn.RedisDistributedLock.acquire")
@patch("common.redis_conn.RedisDistributedLock.release")
def test_graphrag_lock(mock_release, mock_acquire):
    # Simulating GraphRAG indexing lock wrapping
    mock_acquire.return_value = True
    
    kb_id = "test_kb"
    lock_name = f"graphrag_task_{kb_id}"
    
    with RedisDistributedLock(lock_name, timeout=60) as lock:
        assert lock.lock_name == f"devrag:lock:graphrag_task_test_kb"
        
    mock_acquire.assert_called()
    mock_release.assert_called()
