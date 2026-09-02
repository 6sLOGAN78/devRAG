## Objective
Initialize the Python Quart ASGI server to handle AI/ML and Agent-specific HTTP requests.

## Why Now?
Certain APIs (like LLM interactions, deepdoc parsing, agent execution) must run in Python. We need the async ASGI server ready.

## Dependencies
- Phase 01

## Implementation Tasks
- [ ] Create Quart app instance.
- [ ] Define base blueprints (`/api/v1/ml`, `/api/v1/agents`).
- [ ] Add CORS middleware for Quart.
- [ ] Add `/health` endpoint.
- [ ] Setup `api/ragflow_server.py` as entry point (using uvicorn or hypercorn).

## Components
- Quart HTTP Server
- Blueprint Router

## Files
- `api/ragflow_server.py`
- `api/apps/__init__.py`

## Interfaces
- Exposes `GET /api/v1/ml/health`

## Data Changes
N/A

## Data Flow
Client -> Quart Engine -> Handler -> Response

## Testing
- Unit test blueprint health endpoint.

## Deliverable
A running Python ASGI server.

## Definition of Done
- `python api/ragflow_server.py` starts successfully.
- `curl localhost:9381/api/v1/ml/health` returns 200 OK.

## Next Subphase
03-authentication-flow