from typing import Dict, List, Any, Set
from .registry import NodeRegistry
from .component.base import AgentNode

class GraphValidationError(Exception):
    pass

class AgentGraph:
    """
    Static DAG representation of an agent workflow.
    Validates and stores topological ordering.
    """
    def __init__(self, definition: Dict[str, Any]):
        self.version = definition.get("version", 1)
        self.nodes_dict: Dict[str, AgentNode] = {}
        self.edges: List[Dict[str, str]] = definition.get("edges", [])
        self.inputs_map: Dict[str, Dict[str, str]] = {}
        
        self._parse_nodes(definition.get("nodes", []))
        self._validate_edges()
        self.topological_order: List[str] = self._compute_topological_sort()

    def _parse_nodes(self, nodes_data: List[Dict[str, Any]]):
        for node_data in nodes_data:
            node_id = node_data.get("id")
            node_type = node_data.get("type")
            if not node_id:
                raise GraphValidationError("Node is missing an 'id'.")
            if not node_type:
                raise GraphValidationError(f"Node '{node_id}' is missing a 'type'.")
            if node_id in self.nodes_dict:
                raise GraphValidationError(f"Duplicate node ID found: '{node_id}'")
            
            # Lookup in registry. Will raise ValueError if unknown, which satisfies structural validation
            try:
                node_class = NodeRegistry.get(node_type)
            except ValueError as e:
                raise GraphValidationError(str(e))
                
            config = node_data.get("config", {})
            self.nodes_dict[node_id] = node_class(node_id, config)
            
            # Extract inputs mapping if present
            # e.g., "inputs": {"value": "node_a.result"}
            self.inputs_map[node_id] = node_data.get("inputs", {})

    def _validate_edges(self):
        for edge in self.edges:
            source = edge.get("source")
            target = edge.get("target")
            if not source or not target:
                raise GraphValidationError("Edge is missing 'source' or 'target'.")
            if source not in self.nodes_dict:
                raise GraphValidationError(f"Edge references unknown source node: '{source}'")
            if target not in self.nodes_dict:
                raise GraphValidationError(f"Edge references unknown target node: '{target}'")
            if source == target:
                raise GraphValidationError(f"Self-loop detected on node: '{source}'")

    def _compute_topological_sort(self) -> List[str]:
        # Kahn's algorithm
        in_degree: Dict[str, int] = {node_id: 0 for node_id in self.nodes_dict}
        adj: Dict[str, List[str]] = {node_id: [] for node_id in self.nodes_dict}
        
        for edge in self.edges:
            u, v = edge["source"], edge["target"]
            adj[u].append(v)
            in_degree[v] += 1
            
        # Deterministic ordering: sort nodes by ID before enqueuing
        zero_in_degree = sorted([n for n, d in in_degree.items() if d == 0])
        
        topo_order = []
        
        while zero_in_degree:
            # Pop the first element (already sorted, deterministic)
            u = zero_in_degree.pop(0)
            topo_order.append(u)
            
            # Sort neighbors to maintain deterministic tie-breaking
            for v in sorted(adj[u]):
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    # Insert while maintaining sorted order?
                    # No, Kahn's with sorting requires us to just append and re-sort or use a priority queue.
                    # For simplicity, just append and re-sort the zero_in_degree list
                    zero_in_degree.append(v)
                    zero_in_degree.sort()
                    
        if len(topo_order) != len(self.nodes_dict):
            # Find the nodes in the cycle
            cycle_nodes = [n for n, d in in_degree.items() if d > 0]
            raise GraphValidationError(f"Graph contains a cycle involving nodes: {', '.join(sorted(cycle_nodes))}")
            
        return topo_order

    @classmethod
    def from_definition(cls, definition: Dict[str, Any]) -> 'AgentGraph':
        return cls(definition)
