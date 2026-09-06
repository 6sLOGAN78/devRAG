import abc
from typing import Any, Dict, Optional
from dataclasses import dataclass

@dataclass
class NodeResult:
    output: Any
    route: Optional[str] = None

class AgentNode(abc.ABC):
    """
    Base class for all executable nodes in an AgentGraph.
    Nodes should remain stateless between executions.
    """
    def __init__(self, node_id: str, config: Optional[Dict[str, Any]] = None):
        self.id = node_id
        self.config = config or {}

    @abc.abstractmethod
    def execute(self, resolved_inputs: Dict[str, Any]) -> Any:
        """
        Execute the node logic.
        
        :param resolved_inputs: A dictionary where values have been resolved
                                from previous node outputs by the GraphRunner.
        :return: The output of this node (typically a Dict), which will be stored
                 in the execution state.
        """
        pass
