import pytest
from unittest.mock import MagicMock, patch
from rag.nlp.retrieval import RetrievalService, RetrievedChunk
from rag.vector_store.base import SearchResult

@pytest.fixture
def mock_vector_store():
    store = MagicMock()
    return store

@pytest.fixture
def retrieval_service(mock_vector_store):
    return RetrievalService(vector_store=mock_vector_store)

@patch('rag.nlp.retrieval.EmbeddingEngine')
@patch('rag.nlp.retrieval.RerankEngine')
def test_reranking_flow_success(mock_rerank_engine_class, mock_embedding_engine_class, mock_vector_store, retrieval_service):
    # Setup mocks
    mock_engine = MagicMock()
    mock_engine.embed.return_value = [[0.1]*384]
    mock_embedding_engine_class.return_value = mock_engine
    
    mock_rerank_engine = MagicMock()
    mock_rerank_engine_class.return_value = mock_rerank_engine
    
    # 2 candidates from hybrid
    mock_vector_store.search.return_value = [
        SearchResult(id="c1", document_id="d1", dataset_id="ds1", content="chunk 1", score=0.9),
        SearchResult(id="c2", document_id="d1", dataset_id="ds1", content="chunk 2", score=0.8)
    ]
    mock_vector_store.search_lexical.return_value = []
    
    # Reranker returns opposite order scores (c2 better than c1)
    mock_rerank_engine.rerank_scores.return_value = [0.1, 0.99]
    
    results = retrieval_service.search("ds1", "query", top_k=2, rerank_enabled=True)
    
    assert len(results) == 2
    # c2 should now be first
    assert results[0].chunk_id == "c2"
    assert results[0].rerank_score == 0.99
    assert results[0].rerank_rank == 1
    
    assert results[1].chunk_id == "c1"
    assert results[1].rerank_score == 0.1
    assert results[1].rerank_rank == 2
    
@patch('rag.nlp.retrieval.EmbeddingEngine')
@patch('rag.nlp.retrieval.RerankEngine')
def test_reranking_fallback(mock_rerank_engine_class, mock_embedding_engine_class, mock_vector_store, retrieval_service):
    # Setup mocks
    mock_engine = MagicMock()
    mock_engine.embed.return_value = [[0.1]*384]
    mock_embedding_engine_class.return_value = mock_engine
    
    mock_rerank_engine = MagicMock()
    mock_rerank_engine_class.return_value = mock_rerank_engine
    
    mock_vector_store.search.return_value = [
        SearchResult(id="c1", document_id="d1", dataset_id="ds1", content="chunk 1", score=0.9),
        SearchResult(id="c2", document_id="d1", dataset_id="ds1", content="chunk 2", score=0.8)
    ]
    mock_vector_store.search_lexical.return_value = []
    
    # Reranker fails
    mock_rerank_engine.rerank_scores.side_effect = Exception("Model Out of Memory")
    
    results = retrieval_service.search("ds1", "query", top_k=2, rerank_enabled=True)
    
    # Should fallback to original hybrid order
    assert len(results) == 2
    assert results[0].chunk_id == "c1"
    assert results[1].chunk_id == "c2"
    
@patch('rag.nlp.retrieval.EmbeddingEngine')
@patch('rag.nlp.retrieval.RerankEngine')
def test_reranking_disabled(mock_rerank_engine_class, mock_embedding_engine_class, mock_vector_store, retrieval_service):
    # Setup mocks
    mock_engine = MagicMock()
    mock_engine.embed.return_value = [[0.1]*384]
    mock_embedding_engine_class.return_value = mock_engine
    
    mock_vector_store.search.return_value = [
        SearchResult(id="c1", document_id="d1", dataset_id="ds1", content="chunk 1", score=0.9),
    ]
    mock_vector_store.search_lexical.return_value = []
    
    results = retrieval_service.search("ds1", "query", top_k=2, rerank_enabled=False)
    
    assert len(results) == 1
    assert results[0].chunk_id == "c1"
    # Engine should never have been initialized
    mock_rerank_engine_class.assert_not_called()
    
@patch('rag.nlp.retrieval.EmbeddingEngine')
@patch('rag.nlp.retrieval.RerankEngine')
def test_mismatched_scores(mock_rerank_engine_class, mock_embedding_engine_class, mock_vector_store, retrieval_service):
    mock_engine = MagicMock()
    mock_engine.embed.return_value = [[0.1]*384]
    mock_embedding_engine_class.return_value = mock_engine
    
    mock_rerank_engine = MagicMock()
    mock_rerank_engine_class.return_value = mock_rerank_engine
    
    mock_vector_store.search.return_value = [
        SearchResult(id="c1", document_id="d1", dataset_id="ds1", content="chunk 1", score=0.9),
        SearchResult(id="c2", document_id="d1", dataset_id="ds1", content="chunk 2", score=0.8)
    ]
    mock_vector_store.search_lexical.return_value = []
    
    # Reranker returns wrong number of scores (e.g. 1 score for 2 chunks)
    mock_rerank_engine.rerank_scores.return_value = [0.1]
    
    # Should safely fallback
    results = retrieval_service.search("ds1", "query", top_k=2, rerank_enabled=True)
    
    assert len(results) == 2
    assert results[0].chunk_id == "c1"
    assert results[1].chunk_id == "c2"

