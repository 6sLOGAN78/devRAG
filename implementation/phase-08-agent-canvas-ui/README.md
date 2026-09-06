# Phase 08: Agent Canvas UI (Frontend)

## Phase Objective
Build the visual drag-and-drop editor using React Flow (`@xyflow/react`) to allow users to construct the JSON agent graphs.

## Why This Phase Comes Here
The backend engine requires JSON graph definitions. Writing these by hand is impossible for users; they need a visual UI.

## Dependencies
Depends on:
- Phase 07 (Graph definitions)

Required by:
- Phase 09 (Chat requires agents)

## Phase Architecture
Frontend React Flow integration communicating with CRUD APIs on the Go/Python backend to save canvas state.

## Subphase Order
01-react-flow-setup -> 02-node-components -> 03-config-drawers -> 04-canvas-api-sync

## Phase Deliverable
A visual workflow editor in the browser.

## Phase Definition of Done
- User can drag nodes, connect edges, configure settings, and save the graph.
- JSON translates perfectly to backend requirements.

## What NOT To Build Yet
Execution log UI (can be deferred).

## Next Phase
Phase 09: Chat & Streaming API

## Distributed Coordination Requirements
- **Canvas Replica Service**: Must use `RedisDistributedLock` to synchronize canvas replica operations across nodes.