## Objective
Implement the Python endpoint/worker that receives tasks, downloads the file from MinIO, runs DeepDoc, and saves chunks to the DB.

## Why Now?
Connects the orchestrator to the actual DeepDoc logic.

## Dependencies
- 02-go-syncer-worker
- Phase 04

## Implementation Tasks
- [ ] Create Python API `/api/v1/ml/parse_document`.
- [ ] Download file from MinIO path.
- [ ] Invoke `DeepDoc` parser based on document strategy.
- [ ] Save output into `document_chunk` table.
- [ ] Update `document_task` progress to `100%` and `SUCCESS`.

## Components
- ML Task Handler
- Chunk Saver

## Files
- `api/apps/ml_handler.py`
- `api/services/parsing_service.py`

## Interfaces
- `POST /api/v1/ml/parse_document`

## Data Changes
Inserts into `document_chunk`. Updates `document_task`.

## Data Flow
Syncer HTTP -> Python API -> MinIO (Read) -> DeepDoc -> DB (Insert Chunks) -> Status (Success)

## Testing
- Integration test triggering the API with a test file in MinIO.

## Deliverable
E2E parsing execution.

## Definition of Done
- A dispatched task successfully produces DB chunks and finishes.

## Next Subphase
04-frontend-progress-ui