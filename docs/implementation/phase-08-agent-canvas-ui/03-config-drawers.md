## Objective
Build the right-side configuration drawers for each node type (e.g., prompt editors, LLM selectors).

## Why Now?
Nodes are useless without parameter configuration.

## Dependencies
- 02-node-components

## Implementation Tasks
- [ ] Create click handler on nodes to open the Right Drawer.
- [ ] Build `LLMForm`: Model select, system prompt textarea, temperature sliders.
- [ ] Build `RetrievalForm`: Dataset multi-select, similarity sliders.
- [ ] Sync form data changes back to the specific node's `data` object in React Flow state.

## Components
- Config Drawers
- Form Components

## Files
- `web/src/pages/agent/form/agent-form/index.tsx`
- `web/src/pages/agent/form/retrieval-form/index.tsx`
- `web/src/components/llm-select/index.tsx`

## Interfaces
N/A

## Data Changes
N/A

## Data Flow
Node Click -> Drawer -> Form Input -> Update React Flow Node Data

## Testing
- Verify that changing a value in the drawer updates the node state.

## Deliverable
Interactive node configuration.

## Definition of Done
- Users can configure specific parameters for every node type.

## Next Subphase
04-canvas-api-sync