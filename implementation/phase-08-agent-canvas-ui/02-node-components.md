## Objective
Create custom UI representations for the React Flow nodes on the canvas.

## Why Now?
Default React Flow nodes are too simple. We need custom styling and handles.

## Dependencies
- 01-react-flow-setup

## Implementation Tasks
- [ ] Build custom `LLMNodeUI`, `RetrievalNodeUI`, etc.
- [ ] Implement custom Source and Target handles (inputs/outputs).
- [ ] Add status indicators (Run, Success, Error) to nodes.
- [ ] Register custom node types with React Flow.

## Components
- Custom Nodes

## Files
- `web/src/components/canvas/custom-nodes.tsx`

## Interfaces
N/A

## Data Changes
N/A

## Data Flow
N/A

## Testing
- Visual verification of node styling and handle connections.

## Deliverable
Polished canvas visualization.

## Definition of Done
- Nodes look professional and handles enforce correct connection logic (e.g., outputs to inputs).

## Next Subphase
03-config-drawers