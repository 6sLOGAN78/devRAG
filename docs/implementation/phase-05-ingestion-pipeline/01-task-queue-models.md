## Objective
Define the database schema for parsing tasks and chunks.

## Why Now?
We need to track the state of asynchronous jobs.

## Dependencies
- Phase 04

## Implementation Tasks
- [ ] Create `document_task` table (id, document_id, status, progress, error_msg).
- [ ] Create `document_chunk` table (id, document_id, content, page_num, bbox, tokens).
- [ ] Update Go/Python ORM models.

## Components
- DB Models

## Files
- `internal/dao/models.go`
- `api/db/db_models.py`

## Interfaces
N/A

## Data Changes
Adds `document_task` and `document_chunk` tables.

## Data Flow
N/A

## Testing
- DB migration verification.

## Deliverable
State tracking models for async parsing.

## Definition of Done
- Tables created.

## Next Subphase
02-go-syncer-worker