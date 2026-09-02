## Objective
Implement the Python SSE endpoint that triggers the Agent graph and yields streamed text tokens.

## Why Now?
Real-time UX is mandatory for LLM applications.

## Dependencies
- 01-chat-session-models
- Phase 07 (Agent Engine)

## Implementation Tasks
- [ ] Python API: `POST /api/v1/chat/completions`.
- [ ] Load Agent Canvas definition from DB.
- [ ] Execute `GraphRunner` with user query.
- [ ] Stream yields from the final LLM Node as SSE text chunks (`data: {"text": "hello"}

`).
- [ ] Save assistant message to DB after completion.

## Components
- SSE Handler
- Graph Integrator

## Files
- `api/apps/chat_handler.py`

## Interfaces
- `POST /api/v1/chat/completions` (text/event-stream)

## Data Changes
Inserts into `chat_message`.

## Data Flow
Client HTTP -> Python SSE -> Graph Engine -> LLM Node Stream -> Yield SSE -> Client

## Testing
- Curl the endpoint and verify chunked SSE output.

## Deliverable
Streaming chat completion API.

## Definition of Done
- Endpoint correctly executes complex graphs and streams text back.

## Next Subphase
03-frontend-chat-ui