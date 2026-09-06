import pytest
from unittest.mock import MagicMock, patch
from agent.component.retrieval import RetrievalNode
from agent.graph import AgentGraph
from agent.runner import GraphRunner
from rag.nlp.retrieval import RetrievedChunk

@pytest.fixture
def mock_retrieval_service():
    with patch('agent.component.retrieval.get_retrieval_service') as mock_get:
        service_mock = MagicMock()
        mock_get.return_value = service_mock
        yield service_mock

def test_retrieval_node_query_resolution(mock_retrieval_service):
    config = {
        "dataset_id": "test_dataset",
        "query": "{{ question }}",
        "top_k": 3
    }
    node = RetrievalNode("retrieval_1", config)
    
    mock_retrieval_service.search.return_value = [
        RetrievedChunk(chunk_id="c1", document_id="d1", dataset_id="test_dataset", content="Answer here", score=0.9, metadata={"source": "doc.pdf"})
    ]
    
    output = node.execute({"question": "What is RRF?"})
    
    mock_retrieval_service.search.assert_called_once_with(
        dataset_id="test_dataset",
        query="What is RRF?",
        top_k=3,
        rerank_enabled=True
    )
    
    assert "--- CHUNK 1 ---" in output["context"]
    assert "[Source: doc.pdf]" in output["context"]
    assert "Answer here" in output["context"]
    assert len(output["chunks"]) == 1

def test_missing_dataset_id():
    config = {
        "query": "{{ question }}",
    }
    node = RetrievalNode("retrieval_1", config)
    
    with pytest.raises(ValueError, match="requires a dataset_id"):
        node.execute({"question": "hello"})

def test_invalid_query():
    config = {
        "dataset_id": "ds1",
        "query": "{{ question }}",
    }
    node = RetrievalNode("retrieval_1", config)
    
    with pytest.raises(ValueError, match="resolved an empty query"):
        node.execute({"question": "   "})
        
def test_empty_results(mock_retrieval_service):
    config = {
        "dataset_id": "test_dataset",
        "query": "{{ question }}",
    }
    node = RetrievalNode("retrieval_1", config)
    mock_retrieval_service.search.return_value = []
    
    output = node.execute({"question": "Empty query?"})
    
    assert output["context"] == ""
    assert output["chunks"] == []

def test_retrieval_failure(mock_retrieval_service):
    config = {
        "dataset_id": "test_dataset",
        "query": "{{ question }}",
    }
    node = RetrievalNode("retrieval_1", config)
    mock_retrieval_service.search.side_effect = Exception("DB Down")
    
    with pytest.raises(RuntimeError, match="Retrieval operation failed: DB Down"):
        node.execute({"question": "Fail please"})

def test_threshold_filtering(mock_retrieval_service):
    config = {
        "dataset_id": "test_dataset",
        "query": "{{ question }}",
        "threshold": 0.8
    }
    node = RetrievalNode("retrieval_1", config)
    
    mock_retrieval_service.search.return_value = [
        RetrievedChunk(chunk_id="c1", document_id="d1", dataset_id="ds", content="Good", score=0.9, rerank_score=0.95),
        RetrievedChunk(chunk_id="c2", document_id="d2", dataset_id="ds", content="Bad", score=0.5, rerank_score=0.4),
        RetrievedChunk(chunk_id="c3", document_id="d3", dataset_id="ds", content="Okay", score=0.85, rerank_score=0.8)
    ]
    
    output = node.execute({"question": "Threshold filter"})
    assert len(output["chunks"]) == 2
    assert "Good" in output["context"]
    assert "Okay" in output["context"]
    assert "Bad" not in output["context"]

def test_graph_integration(mock_retrieval_service):
    # LLM Provider mock
    with patch('agent.component.llm.litellm.completion') as mock_completion:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "RRF combines multiple rankings."
        mock_response.usage = None
        mock_completion.return_value = mock_response

        # Retrieval mock
        mock_retrieval_service.search.return_value = [
            RetrievedChunk(chunk_id="c1", document_id="d1", dataset_id="ds", content="RRF stands for Reciprocal Rank Fusion.", score=0.9)
        ]

        definition = {
            "nodes": [
                {
                    "id": "start",
                    "type": "mock",
                    "config": {"question": "What is RRF?"}
                },
                {
                    "id": "retriever",
                    "type": "retrieval",
                    "config": {
                        "dataset_id": "ds1",
                        "query": "{{ q }}"
                    },
                    "inputs": {
                        "q": "start.question"
                    }
                },
                {
                    "id": "llm",
                    "type": "llm",
                    "config": {
                        "model": "gpt-4",
                        "prompt": "Answer using context:\n{{ ctx }}\nQuestion: {{ q }}"
                    },
                    "inputs": {
                        "q": "start.question",
                        "ctx": "retriever.context"
                    }
                }
            ],
            "edges": [
                {"source": "start", "target": "retriever"},
                {"source": "retriever", "target": "llm"}
            ]
        }
        
        graph = AgentGraph(definition)
        runner = GraphRunner()
        result = runner.run(graph)
        
        assert result.status == "success"
        
        # Verify Retrieval output
        retrieval_output = result.state.get_output("retriever")
        assert "RRF stands for Reciprocal Rank Fusion." in retrieval_output["context"]
        
        # Verify LLM prompt contains context
        messages = mock_completion.call_args.kwargs["messages"]
        prompt = messages[0]["content"]
        assert "Answer using context:" in prompt
        assert "RRF stands for Reciprocal Rank Fusion." in prompt
        assert "Question: What is RRF?" in prompt
        
        # Verify final output
        llm_output = result.state.get_output("llm")
        assert llm_output["text"] == "RRF combines multiple rankings."

