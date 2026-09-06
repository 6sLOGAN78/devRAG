import pytest
from unittest.mock import MagicMock, patch
from agent.component.llm import LLMNode
from agent.graph import AgentGraph
from agent.runner import GraphRunner
from jinja2 import TemplateError
from litellm import Timeout

def test_llm_node_basic_execution():
    config = {
        "model": "gpt-4",
        "prompt": "Answer: {{ question }}"
    }
    node = LLMNode(node_id="llm_1", config=config)
    
    with patch('agent.component.llm.litellm.completion') as mock_completion:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "42"
        mock_response.usage = {"total_tokens": 10}
        mock_completion.return_value = mock_response
        
        output = node.execute({"question": "What is the meaning of life?"})
        
        assert output["text"] == "42"
        assert output["model"] == "gpt-4"
        assert output["usage"]["total_tokens"] == 10
        
        mock_completion.assert_called_once()
        kwargs = mock_completion.call_args.kwargs
        assert kwargs["model"] == "gpt-4"
        assert len(kwargs["messages"]) == 1
        assert kwargs["messages"][0]["content"] == "Answer: What is the meaning of life?"

def test_missing_template_variable():
    config = {
        "model": "gpt-4",
        "prompt": "Answer: {{ missing }}"
    }
    node = LLMNode(node_id="llm_1", config=config)
    
    with pytest.raises(ValueError, match="Template rendering failed"):
        node.execute({"question": "hello"})

def test_system_prompt_rendering():
    config = {
        "model": "gpt-4",
        "system_prompt": "You are {{ identity }}.",
        "prompt": "Say hello."
    }
    node = LLMNode(node_id="llm_1", config=config)
    
    with patch('agent.component.llm.litellm.completion') as mock_completion:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello!"
        mock_completion.return_value = mock_response
        
        node.execute({"identity": "a helpful bot"})
        
        kwargs = mock_completion.call_args.kwargs
        messages = kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a helpful bot."
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "Say hello."

def test_streaming_execution():
    config = {
        "model": "gpt-4",
        "prompt": "Count to 3",
        "stream": True
    }
    node = LLMNode(node_id="llm_1", config=config)
    
    with patch('agent.component.llm.litellm.completion') as mock_completion:
        def mock_stream():
            for word in ["1, ", "2, ", "3"]:
                chunk = MagicMock()
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta.content = word
                yield chunk
                
        mock_completion.return_value = mock_stream()
        
        output = node.execute({})
        assert output["text"] == "1, 2, 3"
        assert output["usage"] is None
        
        mock_completion.assert_called_once()
        assert mock_completion.call_args.kwargs["stream"] is True

def test_provider_timeout_failure():
    config = {
        "model": "gpt-4",
        "prompt": "Hello"
    }
    node = LLMNode(node_id="llm_1", config=config)
    
    with patch('agent.component.llm.litellm.completion') as mock_completion:
        mock_completion.side_effect = Timeout("Request timed out", model="gpt-4", llm_provider="openai")
        
        with pytest.raises(Timeout):
            node.execute({})

def test_llm_in_graph_runner():
    definition = {
        "nodes": [
            {
                "id": "start",
                "type": "mock",
                "config": {"question": "Why?"}
            },
            {
                "id": "llm_node",
                "type": "llm",
                "config": {
                    "model": "mock-model",
                    "prompt": "{{ q }}"
                },
                "inputs": {
                    "q": "start.question"
                }
            },
            {
                "id": "end",
                "type": "mock",
                "inputs": {
                    "final_answer": "llm_node.text"
                }
            }
        ],
        "edges": [
            {"source": "start", "target": "llm_node"},
            {"source": "llm_node", "target": "end"}
        ]
    }
    graph = AgentGraph(definition)
    runner = GraphRunner()
    
    with patch('agent.component.llm.litellm.completion') as mock_completion:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Because!"
        mock_response.usage = None
        mock_completion.return_value = mock_response
        
        result = runner.run(graph)
        
        assert result.status == "success"
        # Verify state propagation
        assert result.state.get_output("end")["final_answer"] == "Because!"
        
        # Verify correct prompt was passed to LLM
        messages = mock_completion.call_args.kwargs["messages"]
        assert messages[0]["content"] == "Why?"


def test_streaming_failure():
    config = {
        "model": "gpt-4",
        "prompt": "Count to 3",
        "stream": True
    }
    node = LLMNode(node_id="llm_1", config=config)
    
    with patch('agent.component.llm.litellm.completion') as mock_completion:
        def mock_stream():
            yield MagicMock(choices=[MagicMock(delta=MagicMock(content="1, "))])
            yield MagicMock(choices=[MagicMock(delta=MagicMock(content="2, "))])
            raise Exception("Stream interrupted")
                
        mock_completion.return_value = mock_stream()
        
        with pytest.raises(Exception, match="Stream interrupted"):
            node.execute({})

def test_empty_response():
    config = {
        "model": "gpt-4",
        "prompt": "Say nothing"
    }
    node = LLMNode(node_id="llm_1", config=config)
    
    with patch('agent.component.llm.litellm.completion') as mock_completion:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None # Or empty string
        mock_completion.return_value = mock_response
        
        output = node.execute({})
        assert output["text"] == ""

from litellm import AuthenticationError, RateLimitError

def test_authentication_failure():
    node = LLMNode(node_id="llm_1", config={"model": "gpt-4", "prompt": "Hi"})
    with patch('agent.component.llm.litellm.completion') as mock_completion:
        mock_completion.side_effect = AuthenticationError("Invalid auth", llm_provider="openai", model="gpt-4", response=MagicMock())
        with pytest.raises(AuthenticationError):
            node.execute({})

def test_rate_limit_failure():
    node = LLMNode(node_id="llm_1", config={"model": "gpt-4", "prompt": "Hi"})
    with patch('agent.component.llm.litellm.completion') as mock_completion:
        mock_completion.side_effect = RateLimitError("Too many requests", llm_provider="openai", model="gpt-4", response=MagicMock())
        with pytest.raises(RateLimitError):
            node.execute({})

def test_malformed_response():
    node = LLMNode(node_id="llm_1", config={"model": "gpt-4", "prompt": "Hi"})
    with patch('agent.component.llm.litellm.completion') as mock_completion:
        # Malformed missing choices
        mock_completion.return_value = MagicMock(choices=[])
        with pytest.raises(Exception):
            node.execute({})
