## Objective
Define the core Agent Graph Runtime, state memory management, and topological sorting logic.

## Why Now?
The foundation of the agent workflow.

## Dependencies
- Phase 06

## Implementation Tasks
- [ ] Define `AgentGraph` and `AgentNode` base classes.
- [ ] Implement `GraphRunner` that performs topological sort of nodes.
- [ ] Implement execution state memory dictionary (passing outputs of Node A as inputs to Node B).
- [ ] Define DB schema for `agent_canvas` (storing the JSON definition).

## Components
- Graph Runner
- Memory State
- DB Schema

## Files
- `agent/graph.py`
- `agent/component/base.py`
- `api/db/db_models.py` (add canvas table)

## Interfaces
N/A

## Data Changes
Adds `agent_canvas` table to MySQL.

## Data Flow
JSON Definition -> GraphRunner -> Execute nodes sequentially/parallel

## Testing
- Unit test topological sorting and state passing with mock nodes.

## Deliverable
Core execution runtime.

## Definition of Done
- Engine can parse a valid DAG and execute dummy nodes in order.

## Next Subphase
02-llm-node