# Document API Contract

## Overview
Documents represent raw files uploaded into a specific `Dataset`.

## Endpoints

### `POST /api/v1/document/upload`
Uploads a document.
**Requires:** Authentication and valid tenant ownership of the provided dataset.
**Payload (Multipart):**
- `dataset_id` (string)
- `file` (file)
**Response:**
Returns the Document metadata including `id`, `parse_status: pending`, and MinIO storage details.

### `GET /api/v1/document/list?dataset_id=<id>`
Lists documents inside a dataset.
**Requires:** Authentication and valid tenant membership of the dataset.

### `DELETE /api/v1/document/:id`
Deletes a document and attempts MinIO cleanup.
**Requires:** Authentication and tenant ownership of the document.
**Behavior:**
- Hard deletes from the `document` table.
- Best-effort cleanup of MinIO `minio_path`. If DB deletion succeeds but MinIO fails, the DB record is gone, and the object is soft-orphaned.

## DB Isolation
- Operations enforce `WHERE tenant_id = ?` dynamically at the DAO layer.
- Uploads validate dataset ownership securely prior to MinIO consumption.

## Object Key Strategy
`tenant/{tenant_id}/dataset/{dataset_id}/document/{document_id}/original`
This prevents traversal risks and path collisions.
