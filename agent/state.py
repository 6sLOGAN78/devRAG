from typing import Any, Dict, Optional

class ExecutionState:
    """
    Mutable state isolated to a single graph execution run.
    """
    def __init__(self, execution_id: str):
        self.execution_id = execution_id
        # node_id -> output dict
        self._outputs: Dict[str, Any] = {}
        # node_id -> Exception
        self._errors: Dict[str, Exception] = {}
        
    def set_output(self, node_id: str, output: Any):
        self._outputs[node_id] = output
        
    def get_output(self, node_id: str) -> Optional[Any]:
        return self._outputs.get(node_id)
        
    def set_error(self, node_id: str, error: Exception):
        self._errors[node_id] = error
        
    def has_error(self, node_id: str) -> bool:
        return node_id in self._errors

    def get_all_outputs(self) -> Dict[str, Any]:
        return self._outputs.copy()
