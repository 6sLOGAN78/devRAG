## Objective
Update the frontend to show real-time parsing progress and status.

## Why Now?
Users need feedback that their document is being processed.

## Dependencies
- 03-python-task-executor

## Implementation Tasks
- [ ] Create Go API `GET /api/v1/document/status` (or use SSE/WebSockets for updates).
- [ ] Update React UI Document list to poll or listen for status changes.
- [ ] Render Progress Bar and Status Badges.

## Components
- Progress UI
- Status API

## Files
- `internal/handler/document.go`
- `web/src/pages/datasets/detail.tsx`

## Interfaces
- `GET /api/v1/document/status`

## Data Changes
N/A

## Data Flow
DB -> Go API -> React UI

## Testing
- Upload file, watch progress bar update to 100%.

## Deliverable
Real-time UI feedback loop.

## Definition of Done
- UI correctly reflects backend async job state.

## Next Subphase
Phase 06 - 01-vector-db-adapters