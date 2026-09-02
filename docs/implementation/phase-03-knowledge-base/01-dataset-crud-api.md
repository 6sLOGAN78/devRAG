## Objective
Implement backend CRUD APIs for Datasets (Knowledge Bases).

## Why Now?
Documents belong to Datasets. Datasets must exist first.

## Dependencies
- Phase 02 Auth

## Implementation Tasks
- [ ] Define `dataset` DB table (id, name, tenant_id, description, status).
- [ ] Go: Implement DAO and Service for Dataset CRUD.
- [ ] Go: Expose `POST /api/v1/dataset`, `GET /api/v1/dataset/list`, `DELETE /api/v1/dataset/:id`.

## Components
- Dataset Handler
- Dataset Service

## Files
- `internal/dao/models.go`
- `internal/handler/dataset.go`
- `internal/service/dataset.go`

## Interfaces
- REST API for Dataset CRUD.

## Data Changes
Adds `dataset` table.

## Data Flow
API -> Service -> DB

## Testing
- API Integration tests for Dataset CRUD (with mocked/real JWT).

## Deliverable
Dataset management backend.

## Definition of Done
- CRUD endpoints work and properly isolate by `tenant_id`.

## Next Subphase
02-document-upload-api