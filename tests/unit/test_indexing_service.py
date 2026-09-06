import pytest
from unittest.mock import patch, MagicMock
from api.services.indexing_service import IndexingService
from api.db.db_models import DocumentChunk
from rag.vector_store.base import VectorRecord

@patch('api.services.indexing_service.EmbeddingEngine')
@patch('api.services.indexing_service.InfinityAdapter')
def test_index_document_success(mock_infinity_adapter, mock_embedding_engine):
    mock_engine_instance = MagicMock()
    mock_embedding_engine.return_value = mock_engine_instance
    # Simulate embedding 2 texts
    mock_engine_instance.embed.return_value = [[0.1]*384, [0.2]*384]
    
    mock_vector_store = MagicMock()
    mock_infinity_adapter.return_value = mock_vector_store
    
    service = IndexingService()
    
    chunks = [
        DocumentChunk(id="c1", document_id="d1", content="hello"),
        DocumentChunk(id="c2", document_id="d1", content="world")
    ]
    
    service.index_document("d1", "ds1", chunks)
    
    # Assert VectorDB initialization and idempotency cleanup
    mock_vector_store.create_index.assert_called_once_with("idx_ds1", dimensions=384)
    mock_vector_store.delete.assert_called_once_with("idx_ds1", "d1")
    
    # Assert Embedding engine was called correctly
    mock_engine_instance.embed.assert_called_once_with(["hello", "world"])
    
    # Assert Bulk Insert was called with correct mappings
    mock_vector_store.bulk_insert.assert_called_once()
    args, kwargs = mock_vector_store.bulk_insert.call_args
    index_name = args[0]
    records = args[1]
    
    assert index_name == "idx_ds1"
    assert len(records) == 2
    assert records[0].id == "c1"
    assert records[0].document_id == "d1"
    assert records[0].dataset_id == "ds1"
    assert records[0].content == "hello"
    assert records[0].embedding == [0.1]*384
    
    assert records[1].id == "c2"

@patch('api.services.indexing_service.EmbeddingEngine')
@patch('api.services.indexing_service.InfinityAdapter')
def test_index_empty_chunks(mock_infinity_adapter, mock_embedding_engine):
    service = IndexingService()
    service.index_document("d1", "ds1", [])
    mock_infinity_adapter.return_value.bulk_insert.assert_not_called()

@patch('api.services.indexing_service.EmbeddingEngine')
@patch('api.services.indexing_service.InfinityAdapter')
def test_index_idempotency_deletion_error_ignored(mock_infinity_adapter, mock_embedding_engine):
    # If deletion fails (e.g., table doesn't exist yet), it should catch the warning and proceed
    mock_vector_store = MagicMock()
    mock_infinity_adapter.return_value = mock_vector_store
    mock_vector_store.delete.side_effect = Exception("Table not found")
    
    mock_engine_instance = MagicMock()
    mock_embedding_engine.return_value = mock_engine_instance
    mock_engine_instance.embed.return_value = [[0.1]*384]
    
    service = IndexingService()
    chunks = [DocumentChunk(id="c1", document_id="d1", content="hello")]
    
    # Should not raise exception
    service.index_document("d1", "ds1", chunks)
    
    mock_vector_store.bulk_insert.assert_called_once()
