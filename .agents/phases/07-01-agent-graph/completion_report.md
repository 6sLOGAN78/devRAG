# Phase 07-01 Agent Graph Execution Model Completion Report

## 1. Summary
Implemented the foundational DAG execution runtime for the Agent subsystem. This handles JSON graph definition loading, strict structural validation, topological sorting (Kahn's Algorithm), and execution state management. It provides a generic interface `AgentNode` that subsequent phases (e.g., LLM Node) can implement natively without modifying the core execution engine. The implementation incorporates `peewee` ORM models to store canvas definitions while cleanly separating runtime state from persisted layout definitions.

## 2. Files Changed
* `api/db/db_models.py` (Modified)
  * Added `AgentCanvas` schema for persistent storage of graph definitions mapped to tenants.
* `api/db/migrate_agent_canvas.py` (Created)
  * Added script to safely create the table and execute the Peewee migration against the MySQL cluster.
* `agent/component/base.py` (Created)
  * Defined abstract base classes `AgentNode`.
* `agent/registry.py` (Created)
  * Implemented `NodeRegistry` to route node string types from JSON to corresponding class types (includes `MockNode` for testing).
* `agent/state.py` (Created)
  * Contains `ExecutionState` to track execution output completely isolated by `execution_id`.
* `agent/graph.py` (Created)
  * Houses `AgentGraph` containing parsing, validation, and topological sorting mechanisms.
* `agent/runner.py` (Created)
  * Exposes `GraphRunner` to sequentially execute valid DAGs and propagate state between edges.
* `tests/unit/test_agent_graph.py` (Created)
  * Added rigorous unit testing mapping 11 distinct success and failure topologies (cycles, disjointed graphs, propagation fail-fast).

## 3. Final Architecture
```text
      JSON Definition (from agent_canvas)
                         |
                         v
                    AgentGraph
          [Parses, Validates, Kahn's Topo Sort]
                         |
                         v
                    GraphRunner
          [Orchestrates execution of DAG]
                         |
             +-----------+-----------+
             |                       |
             v                       v
      ExecutionState            NodeRegistry
   [Isolated run state]       [Dynamically loads]
             |                       |
             +-----------+-----------+
                         |
                         v
                   Mock/Math Nodes 
```

## 4. Graph Schema
The `AgentCanvas` `graph_definition` is stored using MySQL's native JSON support (via Peewee `TextField` for generic schema compatibility) under the following layout:
```json
{
  "version": 1,
  "nodes": [
    {
      "id": "node_a",
      "type": "math",
      "config": {
         "op": "add",
         "value": 10
      },
      "inputs": {
         "input": "__start__.initial"
      }
    },
    {
      "id": "node_b",
      "type": "math",
      "config": {},
      "inputs": {
         "input": "node_a.result"
      }
    }
  ],
  "edges": [
    {
      "source": "node_a",
      "target": "node_b"
    }
  ]
}
```

## 5. Node Contract
```python
class AgentNode(abc.ABC):
    def __init__(self, node_id: str, config: Optional[Dict[str, Any]] = None):
        self.id = node_id
        self.config = config or {}

    @abc.abstractmethod
    def execute(self, resolved_inputs: Dict[str, Any]) -> Any:
        pass
```
Future nodes only need to implement `execute()` and return a dictionary (or an object). The `GraphRunner` will ensure that any requested data from upstream nodes is mapped directly into `resolved_inputs`.

## 6. State Contract
* **Output Storage**: Outputs are written to `ExecutionState` under the specific `node_id`. 
* **Downstream Resolution**: The runner parses the `inputs_map` (e.g., `{"input_key": "upstream_node.output_field"}`). It crawls `ExecutionState.get_output("upstream_node")` and retrieves the correct dictionary property before invoking the downstream node.
* **State Isolation**: Passed explicitly through memory during execution (`ExecutionState` initialized securely per `uuid4()`). No module-level or database state bleeding occurs.

## 7. Topological Ordering
* **Algorithm**: Kahn's Algorithm. 
* **Cycle Handling**: Tracks the count of processed nodes versus graph capacity. If it mismatches, it identifies nodes with `in_degree > 0` and forcefully aborts execution via `GraphValidationError("Graph contains a cycle...")`.
* **Deterministic Ordering**: Sorts node IDs lexicographically before pushing to processing queue. 

## 8. Database
* **Schema**: `AgentCanvas` (id, tenant_id, name, description, graph_definition, version, created_by, timestamps).
* **Migration**: Tested via `migrate_agent_canvas.py` executing `db.create_tables()`.
* **Ownership**: Bound contextually by `tenant_id` allowing RLS and API separation.
* **JSON Storage**: Relies on raw `TextField` parsed on load, identical to chunks layout mapping.

## 9. Error Handling
* **Validation Failure**: Missing keys, missing nodes, duplicated IDs raise `GraphValidationError` *before* execution starts.
* **Cycle**: Caught during Kahn's graph sort. Execution is blocked.
* **Unknown Node**: Raises structural validation error immediately mapping off `NodeRegistry`.
* **Execution Failure**: Logs the node failure context and safely returns an `ExecutionResult` terminating sequentially blocked downstream nodes. Successful independent branches preceding the crash remain intact and queryable inside the returned `ExecutionState`.

## 10. Tests
* **tests added**: 1 module (`tests/unit/test_agent_graph.py`).
* **tests executed**: 11 unique assertions testing: DAG linear propagation, DAG diamond execution, multiple-root traversal, Cycle rejection, self-loop blocking, duplication prevention, missing references, sequential failure halt state integrity, and precise explicit input extraction.
* **pass/fail**: 11 passed, 0 failed.

## 11. Known Limitations
* **Parallel Execution**: While the DAG perfectly calculates dependencies suitable for multi-threaded/async execution, the actual `GraphRunner.run` loop is currently strictly sequential (depth/topological-first). 
* **Execution History**: The graph *definition* persists in MySQL, but we are not currently sinking historical *execution runs* back into the database. Outputs remain transient for the duration of the request/API thread lifecycle.

## 12. Next Phase Readiness
`Phase 07-02 — LLM Node` is fully unblocked. The LLM Node can be instantiated easily by subclassing `AgentNode`, adding itself to `NodeRegistry.register("llm", LLMNode)`, extracting API properties out of `self.config`, resolving prompts off `resolved_inputs`, and yielding dictionaries for downstream tasks! No changes to `GraphRunner` or `AgentGraph` are strictly required.
