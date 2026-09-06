## Architecture
- **Discovered Architecture**: RAGFlow uses Redis Streams (`te.1.common`) heavily. However, devRAG's ingestion pipeline specifications (`01-task-queue-models.md` and `03-python-task-executor.md`) define a different mechanism: a database-backed task queue (`document_task`) dispatched via HTTP POST to a Python API (`/api/v1/ml/parse_document`).
- **Dispatch Mechanism Selected**: Database polling using MySQL's `FOR UPDATE SKIP LOCKED` and Go HTTP dispatch.
- **Why**: It strictly aligns with the explicitly planned devRAG ingestion phase architecture documentation rather than retrofitting raw RAGFlow Redis behaviors where we have explicitly redefined them as API-first in `03-python-task-executor.md`.

## Task Lifecycle
- **State Machine**: `unstart` -> `running` (claimed by Go Syncer) -> (HTTP dispatch to Python worker) -> `success` / `failed` (resolved by Python worker upon parsing success/failure).
- **Claiming Semantics**: Go runs multiple `syncer.Run` goroutines which execute `SELECT ... FOR UPDATE SKIP LOCKED` within a database transaction, fetching up to `BatchSize` eligible tasks.
- **Failure Semantics**: If the Go-to-Python HTTP dispatch fails entirely (timeout, 5xx, or network failure), the Syncer falls back and updates the task status to `failed` and writes an `error_msg`. Stale tasks (where Python accepts the payload but crashes) remain in `running` and require a watchdog/stale-task recovery (to be addressed if requested later).
- **Guarantees**: At-least-once HTTP dispatch for tasks successfully claimed from DB.

## Concurrency
- **Number of Workers**: Controlled by configurable `BatchSize` per poll interval.
- **Maximum in-flight tasks**: Regulated by a semaphore (`cfg.Syncer.MaxInFlight`).
- **Locking Strategy**: `FOR UPDATE SKIP LOCKED`.
- **Duplicate-prevention Strategy**: Database transaction updates `unstart` to `running` atomically before dispatching. 

## Files Changed
- `internal/config/config.go` (added SyncerConfig)
- `internal/syncer/syncer.go` (created Syncer implementation)
- `internal/syncer/syncer_test.go` (unit test stub)
- `tests/integration/syncer_integration_test.go` (concurrent test verification)
- `cmd/server/ragflow_server.go` (added context cancellation, server graceful shutdown, and wired syncer go-routine)

## Tests
- `TestSyncerConcurrency` executes 3 simultaneous Syncer processes against the `document_task` database and mocks a Python backend. It verifies exactly 5 dispatches are performed for 5 tasks, proving no race conditions or duplicate claims. `go test -race` passes with zero data races.

## Risks
- **Stale Task Recovery**: If a Python worker receives a task but the process OOM kills during processing, the task will permanently remain `running`. A timeout watchdog (e.g. recovering tasks `running` for > 30 minutes) is required.

## Next Phase
05-03-python-task-executor (The component which receives the `/api/v1/ml/parse_document` request from the Go Syncer).
