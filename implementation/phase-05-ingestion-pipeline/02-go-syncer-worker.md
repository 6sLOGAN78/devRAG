## Objective
Implement a Go background daemon that scans for pending tasks and dispatches them.

## Why Now?
Go is highly concurrent and suitable for orchestrating thousands of tasks.

## Dependencies
- 01-task-queue-models

## Implementation Tasks
- [ ] Create a ticker/cron job in Go (`internal/syncer`).
- [ ] Scan `document_task` where `status = UNSTART`.
- [ ] Call the Python API endpoint (or push to Redis queue) to trigger parsing.
- [ ] Update status to `RUNNING`.

## Components
- Go Syncer

## Files
- `internal/syncer/syncer.go`
- `cmd/ragflow_server.go` (start syncer routine)

## Interfaces
- Outbound HTTP call to Python ML API (or Redis RPUSH).

## Data Changes
Updates `status` in `document_task`.

## Data Flow
DB Timer -> Syncer -> Python API -> DB Update

## Testing
- Unit test task selection logic (avoiding race conditions using `SELECT FOR UPDATE`).

## Deliverable
Task orchestration daemon.

## Definition of Done
- Syncer successfully picks up tasks and dispatches them exactly once.

## Next Subphase
03-python-task-executor