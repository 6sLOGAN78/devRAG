import pytest
from agent.graph import AgentGraph, GraphValidationError
from agent.runner import GraphRunner
from agent.registry import NodeRegistry, AgentNode

# A mock node that just adds an input to its config to test state propagation
class MathNode(AgentNode):
    def execute(self, resolved_inputs):
        op = self.config.get("op", "add")
        val = self.config.get("value", 0)
        in_val = resolved_inputs.get("input", 0)
        
        if op == "add":
            return {"result": in_val + val}
        elif op == "mult":
            return {"result": in_val * val}
        elif op == "fail":
            raise ValueError("Intentional failure")
        return {"result": in_val}

NodeRegistry.register("math", MathNode)

class AppendNode(AgentNode):
    def execute(self, resolved_inputs):
        lst = resolved_inputs.get("list", [])
        return {"list": lst + [self.id]}

NodeRegistry.register("append", AppendNode)

def test_linear_dag():
    definition = {
        "nodes": [
            {"id": "a", "type": "append"},
            {"id": "b", "type": "append", "inputs": {"list": "a.list"}},
            {"id": "c", "type": "append", "inputs": {"list": "b.list"}}
        ],
        "edges": [
            {"source": "a", "target": "b"},
            {"source": "b", "target": "c"}
        ]
    }
    graph = AgentGraph(definition)
    assert graph.topological_order == ["a", "b", "c"]
    
    runner = GraphRunner()
    result = runner.run(graph)
    assert result.status == "success"
    assert result.state.get_output("c") == {"list": ["a", "b", "c"]}

def test_diamond_dag():
    definition = {
        "nodes": [
            {"id": "a", "type": "math", "config": {"op": "add", "value": 5}},
            {"id": "b", "type": "math", "config": {"op": "mult", "value": 2}, "inputs": {"input": "a.result"}},
            {"id": "c", "type": "math", "config": {"op": "add", "value": 10}, "inputs": {"input": "a.result"}},
            {"id": "d", "type": "math", "config": {"op": "add", "value": 0}, "inputs": {"input": "b.result"}}
        ],
        "edges": [
            {"source": "a", "target": "b"},
            {"source": "a", "target": "c"},
            {"source": "b", "target": "d"},
            {"source": "c", "target": "d"}
        ]
    }
    graph = AgentGraph(definition)
    
    assert graph.topological_order.index("a") < graph.topological_order.index("b")
    assert graph.topological_order.index("a") < graph.topological_order.index("c")
    assert graph.topological_order.index("b") < graph.topological_order.index("d")
    assert graph.topological_order.index("c") < graph.topological_order.index("d")
    
    runner = GraphRunner()
    result = runner.run(graph, initial_inputs={"input": 0})
    assert result.status == "success"
    # a = 5, b = 10, c = 15, d reads b.result=10
    assert result.state.get_output("d") == {"result": 10}
    assert result.state.get_output("c") == {"result": 15}

def test_cycle_detection():
    definition = {
        "nodes": [
            {"id": "a", "type": "mock"},
            {"id": "b", "type": "mock"}
        ],
        "edges": [
            {"source": "a", "target": "b"},
            {"source": "b", "target": "a"}
        ]
    }
    with pytest.raises(GraphValidationError, match="Graph contains a cycle"):
        AgentGraph(definition)

def test_missing_node():
    definition = {
        "nodes": [
            {"id": "a", "type": "mock"}
        ],
        "edges": [
            {"source": "a", "target": "b"}
        ]
    }
    with pytest.raises(GraphValidationError, match="Edge references unknown target node: 'b'"):
        AgentGraph(definition)

def test_duplicate_node():
    definition = {
        "nodes": [
            {"id": "a", "type": "mock"},
            {"id": "a", "type": "mock"}
        ]
    }
    with pytest.raises(GraphValidationError, match="Duplicate node ID"):
        AgentGraph(definition)

def test_self_loop():
    definition = {
        "nodes": [
            {"id": "a", "type": "mock"}
        ],
        "edges": [
            {"source": "a", "target": "a"}
        ]
    }
    with pytest.raises(GraphValidationError, match="Self-loop detected"):
        AgentGraph(definition)

def test_unknown_node_type():
    definition = {
        "nodes": [
            {"id": "a", "type": "nonexistent"}
        ]
    }
    with pytest.raises(GraphValidationError, match="Unsupported node type"):
        AgentGraph(definition)

def test_failure_propagation():
    definition = {
        "nodes": [
            {"id": "a", "type": "mock"},
            {"id": "b", "type": "math", "config": {"op": "fail"}},
            {"id": "c", "type": "mock"}
        ],
        "edges": [
            {"source": "a", "target": "b"},
            {"source": "b", "target": "c"}
        ]
    }
    graph = AgentGraph(definition)
    runner = GraphRunner()
    result = runner.run(graph)
    
    assert result.status == "failure"
    assert result.failed_node == "b"
    assert result.state.get_output("a") is not None
    assert result.state.get_output("c") is None

def test_state_isolation():
    definition = {
        "nodes": [
            {"id": "a", "type": "math", "config": {"op": "add", "value": 0}, "inputs": {"input": "__start__.val"}}
        ]
    }
    graph = AgentGraph(definition)
    runner = GraphRunner()
    
    r1 = runner.run(graph, initial_inputs={"val": 10})
    r2 = runner.run(graph, initial_inputs={"val": 100})
    
    assert r1.state.get_output("a")["result"] == 10
    assert r2.state.get_output("a")["result"] == 100

def test_multiple_roots_and_terminals():
    definition = {
        "nodes": [
            {"id": "a", "type": "mock"},
            {"id": "b", "type": "mock"},
            {"id": "c", "type": "mock"},
            {"id": "d", "type": "mock"}
        ],
        "edges": [
            {"source": "a", "target": "c"},
            {"source": "b", "target": "c"},
            {"source": "c", "target": "d"}
        ]
    }
    graph = AgentGraph(definition)
    # Roots: a, b. Terminal: d.
    assert set(graph.topological_order[:2]) == {"a", "b"}
    assert graph.topological_order[2] == "c"
    assert graph.topological_order[3] == "d"
    
    runner = GraphRunner()
    res = runner.run(graph)
    assert res.status == "success"
    # All executed
    for node in ["a", "b", "c", "d"]:
        assert res.state.get_output(node) is not None


def test_explicit_state_passing():
    definition = {
        "nodes": [
            {"id": "a", "type": "math", "config": {"op": "add", "value": 10}, "inputs": {"input": "__start__.initial"}},
            {"id": "b", "type": "math", "config": {"op": "mult", "value": 2}, "inputs": {"input": "a.result"}},
            {"id": "c", "type": "math", "config": {"op": "add", "value": 5}, "inputs": {"input": "b.result"}}
        ],
        "edges": [
            {"source": "a", "target": "b"},
            {"source": "b", "target": "c"}
        ]
    }
    graph = AgentGraph(definition)
    runner = GraphRunner()
    result = runner.run(graph, initial_inputs={"initial": 0})
    
    assert result.status == "success"
    assert result.state.get_output("a")["result"] == 10
    assert result.state.get_output("b")["result"] == 20
    assert result.state.get_output("c")["result"] == 25
