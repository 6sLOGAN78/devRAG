## Objective
Define DB schema and APIs for managing chat sessions and message history.

## Why Now?
Chat is stateful; previous messages must be stored and passed to the LLM.

## Dependencies
- Phase 08

## Implementation Tasks
- [ ] Define `chat_session` table (id, user_id, agent_id, title).
- [ ] Define `chat_message` table (id, session_id, role, content, citations).
- [ ] Go API: CRUD for sessions and fetching history.

## Components
- Session DB Models
- History API

## Files
- `internal/dao/models.go`
- `internal/handler/chat.go`

## Interfaces
- `GET /api/v1/chat/session`
- `GET /api/v1/chat/message/:session_id`

## Data Changes
Adds `chat_session` and `chat_message` tables.

## Data Flow
API -> DB -> Client

## Testing
- Unit test creating a session and appending messages.

## Deliverable
Chat history backend.

## Definition of Done
- Sessions can be created and history retrieved.

## Next Subphase
02-sse-streaming-api