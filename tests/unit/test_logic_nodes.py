import pytest
from unittest.mock import patch, MagicMock

from agent.component.logic import SwitchNode, CategorizeNode, CodeNode
from agent.graph import AgentGraph
from agent.runner import GraphRunner
from agent.component.base import NodeResult

def test_switch_node():
    config = {
        "expression": "{% if score > 0.8 %}high{% else %}low{% endif %}"
    }
    node = SwitchNode("switch_1", config)
    
    # Test 'high' route
    res = node.execute({"score": 0.9})
    assert isinstance(res, NodeResult)
    assert res.route == "high"
    assert res.output["route"] == "high"
    
    # Test 'low' route
    res = node.execute({"score": 0.5})
    assert res.route == "low"

def test_categorize_node():
    config = {
        "categories": ["billing", "tech", "sales"],
        "prompt": "Text: {{ text }}"
    }
    node = CategorizeNode("cat_1", config)
    
    with patch("agent.component.logic.litellm.completion") as mock_completion:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "tech"
        mock_completion.return_value = mock_response
        
        res = node.execute({"text": "My server is down"})
        
        assert isinstance(res, NodeResult)
        assert res.route == "tech"
        assert res.output["category"] == "tech"
        
        # Verify the system prompt has categories
        kwargs = mock_completion.call_args.kwargs
        sys_prompt = kwargs["messages"][0]["content"]
        assert "[billing, tech, sales]" in sys_prompt

def test_code_node_safe_execution():
    config = {
        "code": "output['summary'] = inputs['a'] + inputs['b']"
    }
    node = CodeNode("code_1", config)
    
    res = node.execute({"a": 10, "b": 20})
    assert res == {"summary": 30}

def test_code_node_restricted():
    # Attempting to import os should fail
    config = {
        "code": "import os\noutput['dir'] = os.getcwd()"
    }
    node = CodeNode("code_1", config)
    with pytest.raises(RuntimeError):
        node.execute({})
        
    # Attempting to access dunder methods should fail
    config = {
        "code": "output['bad'] = inputs.__class__.__name__"
    }
    node = CodeNode("code_2", config)
    with pytest.raises(RuntimeError):
        node.execute({"a": 1})

def test_graph_routing_execution():
    # Graph with SwitchNode that routes to A or B
    definition = {
        "nodes": [
            {
                "id": "start",
                "type": "mock",
                "config": {"score": 0.9}
            },
            {
                "id": "switch",
                "type": "switch",
                "config": {
                    "expression": "{% if score > 0.8 %}high{% else %}low{% endif %}"
                },
                "inputs": {
                    "score": "start.score"
                }
            },
            {
                "id": "high_node",
                "type": "mock",
                "config": {"msg": "Hit High"}
            },
            {
                "id": "low_node",
                "type": "mock",
                "config": {"msg": "Hit Low"}
            }
        ],
        "edges": [
            {"source": "start", "target": "switch"},
            {"source": "switch", "target": "high_node", "route": "high"},
            {"source": "switch", "target": "low_node", "route": "low"}
        ]
    }
    
    graph = AgentGraph(definition)
    runner = GraphRunner()
    result = runner.run(graph)
    
    assert result.status == "success"
    
    # high_node should have executed
    assert result.state.get_output("high_node") == {"msg": "Hit High"}
    
    # low_node should have been skipped
    assert result.state.get_output("low_node") is None

    # Test the low route dynamically
    definition["nodes"][0]["config"]["score"] = 0.5
    graph2 = AgentGraph(definition)
    runner2 = GraphRunner()
    result2 = runner2.run(graph2)
    
    assert result2.status == "success"
    assert result2.state.get_output("high_node") is None
    assert result2.state.get_output("low_node") == {"msg": "Hit Low"}

