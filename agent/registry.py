from typing import Dict, Type, Any
from .component.base import AgentNode

class NodeRegistry:
    _registry: Dict[str, Type[AgentNode]] = {}

    @classmethod
    def register(cls, node_type: str, node_class: Type[AgentNode]):
        cls._registry[node_type] = node_class

    @classmethod
    def get(cls, node_type: str) -> Type[AgentNode]:
        if node_type not in cls._registry:
            raise ValueError(f"Unsupported node type: {node_type}")
        return cls._registry[node_type]

class MockNode(AgentNode):
    """A mock node for testing DAG topology and state propagation."""
    def execute(self, resolved_inputs: Dict[str, Any]) -> Any:
        # Mock node simply returns its config and inputs combined, or what is specified
        ret = {}
        if self.config:
            ret.update(self.config)
        if resolved_inputs:
            ret.update(resolved_inputs)
        return ret

NodeRegistry.register("mock", MockNode)
