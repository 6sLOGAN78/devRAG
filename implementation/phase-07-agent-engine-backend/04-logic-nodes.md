## Objective
Implement routing and utility nodes: Switch, Categorize, and Python Code.

## Why Now?
Enables complex, non-linear workflows and custom data transformations.

## Dependencies
- 01-graph-execution-model

## Implementation Tasks
- [ ] Implement `SwitchNode`: Evaluates condition expressions to determine the next graph edge.
- [ ] Implement `CategorizeNode`: Uses a fast/cheap LLM call to classify intent and route.
- [ ] Implement `CodeNode`: Safely executes sandboxed Python code (or restricted `eval`) for data formatting.

## Components
- Logic Nodes

## Files
- `agent/component/switch.py`
- `agent/component/categorize.py`
- `agent/component/code.py`

## Interfaces
N/A

## Data Changes
N/A

## Data Flow
N/A

## Testing
- Unit test Switch logic to ensure it fires the correct downstream edges.

## Deliverable
Advanced workflow capabilities.

## Definition of Done
- Engine supports branching logic based on node outputs.

## Next Subphase
Phase 08 - 01-react-flow-setup