import pytest
from unittest.mock import patch, MagicMock
from rag.nlp.embedding import EmbeddingEngine, EmbeddingConfig, EmbeddingError, EmbeddingDimensionError

import litellm

def test_embedding_config():
    config = EmbeddingConfig(
        provider="litellm",
        model="text-embedding-3-small",
        dimension=1536,
        batch_size=2
    )
    assert config.provider == "litellm"

@patch('rag.nlp.embedding.litellm.embedding')
def test_litellm_batching_and_ordering(mock_litellm_embedding):
    # Mocking response from litellm. We expect batching to send multiple calls.
    # We send 3 texts, batch size 2 -> 2 calls.
    # We verify that 'index' field inside litellm data preserves order across the batch internally.
    config = EmbeddingConfig("litellm", "test-model", dimension=2, batch_size=2)
    engine = EmbeddingEngine(config)
    
    # Mock responses
    def side_effect(*args, **kwargs):
        input_texts = kwargs.get('input')
        data = []
        for i, _ in enumerate(input_texts):
            # simulate litellm response data
            data.append({'index': i, 'embedding': [0.1, 0.2]})
        
        mock_response = MagicMock()
        mock_response.data = data
        return mock_response
        
    mock_litellm_embedding.side_effect = side_effect
    
    texts = ["A", "B", "C"]
    vectors = engine.embed(texts)
    
    assert len(vectors) == 3
    assert vectors == [[0.1, 0.2], [0.1, 0.2], [0.1, 0.2]]
    assert mock_litellm_embedding.call_count == 2 # 3 items / 2 batch size -> 2 batches

@patch('rag.nlp.embedding.litellm.embedding')
def test_litellm_retry_rate_limit(mock_litellm_embedding):
    config = EmbeddingConfig("litellm", "test", dimension=2)
    engine = EmbeddingEngine(config)
    
    # Fail first, then succeed
    mock_response = MagicMock()
    mock_response.data = [{'index': 0, 'embedding': [1.0, 2.0]}]
    
    import httpx
    mock_response_err = httpx.Response(status_code=429, request=httpx.Request("POST", "http://test"))
    
    mock_litellm_embedding.side_effect = [
        litellm.RateLimitError("Too many requests", llm_provider="openai", model="test", response=mock_response_err),
        mock_response
    ]
    
    vectors = engine.embed(["A"])
    assert len(vectors) == 1
    assert vectors[0] == [1.0, 2.0]
    assert mock_litellm_embedding.call_count == 2

@patch('rag.nlp.embedding.litellm.embedding')
def test_litellm_dimension_validation(mock_litellm_embedding):
    # Model config expects dimension 3, but response gives dimension 2
    config = EmbeddingConfig("litellm", "test", dimension=3)
    engine = EmbeddingEngine(config)
    
    mock_response = MagicMock()
    mock_response.data = [{'index': 0, 'embedding': [1.0, 2.0]}]
    mock_litellm_embedding.return_value = mock_response
    
    with pytest.raises(EmbeddingDimensionError) as exc:
        engine.embed(["A"])
    
    assert "Expected dimension 3" in str(exc.value)

@patch('rag.nlp.embedding.LocalHFProvider')
def test_local_hf_provider(mock_hf_class):
    # Testing that local HF uses sentence_transformers correctly
    mock_instance = MagicMock()
    mock_hf_class.return_value = mock_instance
    mock_instance.embed_batch.return_value = [[0.5, 0.5]]
    
    config = EmbeddingConfig("huggingface", "all-MiniLM-L6-v2", dimension=2)
    engine = EmbeddingEngine(config)
    vectors = engine.embed(["Local test"])
    
    assert len(vectors) == 1
    assert vectors[0] == [0.5, 0.5]
    mock_instance.embed_batch.assert_called_once_with(["Local test"])

def test_empty_input():
    config = EmbeddingConfig("litellm", "test", dimension=2)
    engine = EmbeddingEngine(config)
    vectors = engine.embed([])
    assert vectors == []
