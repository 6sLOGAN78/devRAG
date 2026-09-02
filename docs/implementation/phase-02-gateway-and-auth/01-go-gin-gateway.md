## Objective
Initialize the Go Gin HTTP server to act as the primary API gateway for high-throughput endpoints.

## Why Now?
We need an HTTP listener to expose APIs to the frontend.

## Dependencies
- Phase 01

## Implementation Tasks
- [ ] Create Gin engine instance.
- [ ] Define base router groups (e.g., `/api/v1`).
- [ ] Add CORS middleware.
- [ ] Add basic logging and recovery middleware.
- [ ] Implement a `/health` endpoint.
- [ ] Setup `cmd/ragflow_server.go` to start the server.

## Components
- Gin HTTP Server
- Router

## Files
- `cmd/ragflow_server.go`
- `internal/router/router.go`
- `internal/middleware/cors.go`

## Interfaces
- Exposes `GET /api/v1/health`

## Data Changes
N/A

## Data Flow
Client -> Gin Engine -> Handler -> Response

## Testing
- Unit test router health endpoint.

## Deliverable
A running Go API server.

## Definition of Done
- `go run cmd/ragflow_server.go` starts successfully.
- `curl localhost:9380/api/v1/health` returns 200 OK.

## Next Subphase
02-python-quart-service