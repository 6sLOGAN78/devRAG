## Objective
Implement API endpoints to save the React Flow JSON to the database and load it back.

## Why Now?
The canvas must persist to the database to be executable by the backend.

## Dependencies
- 03-config-drawers
- Phase 07 (Backend DB schema)

## Implementation Tasks
- [ ] Go API: `POST /api/v1/agent/canvas/save` and `GET /api/v1/agent/canvas/:id`.
- [ ] Frontend: Implement "Save" button logic (serializing React Flow state).
- [ ] Frontend: Implement data normalization (mapping React Flow edges/nodes to backend DAG schema).
- [ ] Implement load logic on page mount.

## Components
- API Handlers
- Serialization Logic

## Files
- `internal/handler/agent.go`
- `web/src/hooks/use-agent-request.ts`

## Interfaces
- `POST /api/v1/agent/canvas/save`

## Data Changes
Writes JSON to `agent_canvas` table.

## Data Flow
React Flow State -> Serializer -> API -> DB

## Testing
- E2E: Create graph, configure node, save, refresh page, graph loads correctly.

## Deliverable
Persistent Agent Canvas.

## Definition of Done
- Complex graphs can be saved and perfectly restored.

## Next Subphase
Phase 09 - 01-chat-session-models