## Objective
Implement the Document entity and the file upload API, saving raw files to MinIO.

## Why Now?
Users need to ingest data into their Datasets.

## Dependencies
- 01-dataset-crud-api

## Implementation Tasks
- [ ] Define `document` DB table (id, dataset_id, name, size, type, minio_path, parse_status).
- [ ] Go: Implement MinIO client wrapper (`internal/storage/minio.go`).
- [ ] Go: Implement `POST /api/v1/document/upload` which receives `multipart/form-data`, saves to MinIO, and creates a DB record.
- [ ] Go: Implement Document listing and deletion.

## Components
- Document Handler
- Storage Service (MinIO)

## Files
- `internal/storage/minio.go`
- `internal/handler/document.go`
- `internal/service/document.go`

## Interfaces
- `POST /api/v1/document/upload`
- MinIO S3 API

## Data Changes
Adds `document` table.

## Data Flow
Client (Multipart) -> Handler -> MinIO (Save) -> DB (Record) -> Response

## Testing
- Integration test for uploading a dummy PDF and verifying its presence in MinIO and DB.

## Deliverable
File upload pipeline.

## Definition of Done
- Uploaded files are retrievable from MinIO bucket.
- DB tracks document metadata and associates with dataset.

## Next Subphase
03-frontend-auth-and-layout