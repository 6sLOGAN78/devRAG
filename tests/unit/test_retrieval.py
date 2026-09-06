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

def test_empty_query(retrieval_service):
    assert retrieval_service.search("ds1", "") == []
    assert retrieval_service.search("ds1", "   ") == []

def test_rrf_and_deduplication(retrieval_service):
    dense_results = [
        SearchResult(id="c1", document_id="d1", dataset_id="ds1", content="dense only", score=0.9),
        SearchResult(id="c2", document_id="d1", dataset_id="ds1", content="both", score=0.8),
        SearchResult(id="c3", document_id="d1", dataset_id="ds1", content="dense 3", score=0.7),
    ]
    lexical_results = [
        SearchResult(id="c4", document_id="d1", dataset_id="ds1", content="lexical only", score=10.0),
        SearchResult(id="c2", document_id="d1", dataset_id="ds1", content="both", score=5.0),
        SearchResult(id="c1", document_id="d1", dataset_id="ds1", content="dense only", score=1.0),
    ]
    
    # RRF with K=60
    # c1: dense_rank=1, lex_rank=3 -> 1/61 + 1/63 = 0.01639 + 0.01587 = 0.03226
    # c2: dense_rank=2, lex_rank=2 -> 1/62 + 1/62 = 0.01612 + 0.01612 = 0.03225
    # c3: dense_rank=3, lex_rank=none -> 1/63 + 0 = 0.01587
    # c4: dense_rank=none, lex_rank=1 -> 0 + 1/61 = 0.01639
    
    # Expected ranking: c1 (0.03226) > c2 (0.03225) > c4 (0.01639) > c3 (0.01587)
    
    fused = retrieval_service._fuse_results(dense_results, lexical_results, rrf_k=60, top_k=10)
    
    assert len(fused) == 4
    assert fused[0].chunk_id == "c1"
    assert fused[1].chunk_id == "c2"
    assert fused[2].chunk_id == "c4"
    assert fused[3].chunk_id == "c3"
    
    # Check dedup methods
    assert fused[0].retrieval_method == "hybrid"
    assert fused[1].retrieval_method == "hybrid"
    assert fused[2].retrieval_method == "lexical"
    assert fused[3].retrieval_method == "dense"

def test_tie_breaking(retrieval_service):
    # If RRF scores are perfectly tied
    dense_results = [
        SearchResult(id="c1", document_id="d1", dataset_id="ds1", content="c1", score=1.0),
    ]
    lexical_results = [
        SearchResult(id="c2", document_id="d1", dataset_id="ds1", content="c2", score=1.0),
    ]
    
    # Both get 1/(K+1) RRF score.
    # Tie breaker: lexical_rank ASC, dense_rank ASC, chunk_id
    # c1: lex_rank=999999, dense_rank=1
    # c2: lex_rank=1, dense_rank=999999
    # c2 should win tie breaker (lexical_rank 1 < 999999)
    fused = retrieval_service._fuse_results(dense_results, lexical_results, rrf_k=60, top_k=10)
    
    assert fused[0].chunk_id == "c2"
    assert fused[1].chunk_id == "c1"

@patch('rag.nlp.retrieval.EmbeddingEngine')
def test_hybrid_search_flow(mock_engine_class, mock_vector_store, retrieval_service):
    mock_engine = MagicMock()
    mock_engine.embed.return_value = [[0.1]*384]
    mock_engine_class.return_value = mock_engine
    
    mock_vector_store.search.return_value = [
        SearchResult(id="c1", document_id="d1", dataset_id="ds1", content="test", score=0.9)
    ]
    mock_vector_store.search_lexical.return_value = [
        SearchResult(id="c2", document_id="d1", dataset_id="ds1", content="test2", score=10.0)
    ]
    
    results = retrieval_service.search("ds1", "hello", top_k=5, filters={"tenant_id": "t1"})
    
    # Assert vector search called correctly
    mock_vector_store.search.assert_called_once_with(
        "idx_ds1", [0.1]*384, top_k=15, filters={"tenant_id": "t1"}
    )
    mock_vector_store.search_lexical.assert_called_once_with(
        "idx_ds1", "hello", top_k=15, filters={"tenant_id": "t1"}
    )
    
    assert len(results) == 2

@patch('rag.nlp.retrieval.EmbeddingEngine')
def test_lexical_fallback_gracefully(mock_engine_class, mock_vector_store, retrieval_service):
    mock_engine = MagicMock()
    mock_engine.embed.return_value = [[0.1]*384]
    mock_engine_class.return_value = mock_engine
    
    mock_vector_store.search.return_value = [
        SearchResult(id="c1", document_id="d1", dataset_id="ds1", content="test", score=0.9)
    ]
    # Lexical fails
    mock_vector_store.search_lexical.side_effect = Exception("Not Supported")
    
    results = retrieval_service.search("ds1", "hello", top_k=5)
    
    assert len(results) == 1
    assert results[0].chunk_id == "c1"
    assert results[0].retrieval_method == "dense"

@patch('rag.nlp.retrieval.EmbeddingEngine')
def test_dense_failure_bubbles_up(mock_engine_class, mock_vector_store, retrieval_service):
    mock_engine = MagicMock()
    mock_engine_class.return_value = mock_engine
    
    mock_vector_store.search.side_effect = Exception("DB Down")
    
    with pytest.raises(Exception, match="DB Down"):
        retrieval_service.search("ds1", "hello", top_k=5)
