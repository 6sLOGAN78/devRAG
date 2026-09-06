import uuid
import logging
from typing import Dict, Any, Optional

from .graph import AgentGraph
from .state import ExecutionState
from .component.base import NodeResult

logger = logging.getLogger(__name__)

class ExecutionResult:
    def __init__(self, status: str, state: ExecutionState, error: Optional[Exception] = None, failed_node: Optional[str] = None):
        self.status = status # "success" or "failure"
        self.state = state
        self.error = error
        self.failed_node = failed_node

class GraphRunner:
    def __init__(self):
        pass

    def _resolve_inputs(self, node_id: str, graph: AgentGraph, state: ExecutionState) -> Dict[str, Any]:
        """
        Resolves input mappings for the given node from the execution state.
        Supports dotted notation like "node_a.result".
        """
        inputs_map = graph.inputs_map.get(node_id, {})
        resolved = {}
        
        for k, v in inputs_map.items():
            if not isinstance(v, str):
                resolved[k] = v
                continue
                
            parts = v.split('.')
            source_node = parts[0]
            
            output = state.get_output(source_node)
            if output is None:
                resolved[k] = None
                continue
                
            if len(parts) > 1:
                val = output
                for p in parts[1:]:
                    if isinstance(val, dict):
                        val = val.get(p)
                    else:
                        val = None
                        break
                resolved[k] = val
            else:
                resolved[k] = output
                
        return resolved

    def run(self, graph: AgentGraph, initial_inputs: Optional[Dict[str, Any]] = None) -> ExecutionResult:
        execution_id = str(uuid.uuid4())
        logger.info(f"Starting graph execution: {execution_id}")
        
        state = ExecutionState(execution_id)
        
        if initial_inputs:
            state.set_output("__start__", initial_inputs)
            
        node_active = {n: False for n in graph.nodes_dict}
        # Start nodes are active by default
        for n in graph.nodes_dict:
            in_degree = sum(1 for e in graph.edges if e["target"] == n)
            if in_degree == 0:
                node_active[n] = True
            
        for node_id in graph.topological_order:
            if not node_active[node_id]:
                logger.info(f"[Execution: {execution_id}] Skipping node {node_id} (not activated by route)")
                continue
                
            node = graph.nodes_dict[node_id]
            
            try:
                resolved_inputs = self._resolve_inputs(node_id, graph, state)
                logger.info(f"[Execution: {execution_id}] Executing node {node_id}")
                
                result_obj = node.execute(resolved_inputs)
                
                route = None
                if isinstance(result_obj, NodeResult):
                    output = result_obj.output
                    route = result_obj.route
                else:
                    output = result_obj
                    
                state.set_output(node_id, output)
                
                # Activate downstream branches
                outgoing_edges = [e for e in graph.edges if e["source"] == node_id]
                for edge in outgoing_edges:
                    target = edge["target"]
                    edge_route = edge.get("route")
                    
                    if route is not None:
                        if edge_route == route:
                            node_active[target] = True
                    else:
                        node_active[target] = True
                        
            except Exception as e:
                logger.error(f"[Execution: {execution_id}] Node {node_id} of type {type(node).__name__} failed: {e}")
                state.set_error(node_id, e)
                # Fail-fast sequential execution
                return ExecutionResult(status="failure", state=state, error=e, failed_node=node_id)
                
        logger.info(f"[Execution: {execution_id}] Graph execution completed successfully.")
        return ExecutionResult(status="success", state=state)
