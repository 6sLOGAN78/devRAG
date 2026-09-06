# Frontend Knowledge Contract

## Overview
The Knowledge Base UI consumes the Phase 03 APIs via `@tanstack/react-query` to provide a robust caching and mutation framework mapping strictly to real-time `Document` and `Dataset` states without leaking domain logic into components.

## Routing
- `/datasets` -> `DatasetListPage`: Enumerates datasets mapped to the active tenant securely via the `/api/v1/dataset/list` endpoint.
- `/datasets/:datasetId` -> `DatasetDetailPage`: Single Dataset view rendering `documents` natively. Note: Validation of dataset ownership belongs explicitly to the Go backend APIs which enforce `tenant_id` scopes against `dataset_id`.

## React Query Caching Strategies
Stable query keys are heavily relied upon.
- `['datasets']`: Global datasets query. Invalidated immediately upon Dataset Creation or Deletion mapping seamless updates across active UI bounds.
- `['documents', datasetId]`: Scoped documents query bounds. Triggers re-fetch exclusively upon successful file Uploads or Document deletions within that specific context.

## File Upload Semantics
1. Component `FileUploadDialog` maps to S3 multipart interfaces dynamically injecting `/api/v1/document/upload` operations via Axios interceptors carrying auth.
2. File boundaries are actively filtered prior to ingestion minimizing 413 Payload payloads directly intercepting sizes > 50MB natively in React boundaries.
3. Parallel drag-and-drop operations sequence natively relying upon concurrent `mutation.mutateAsync` callbacks securely transmitting individual items sequentially protecting server capacities natively.
4. Upload `AxiosProgressEvent` blocks feed react local states visualizing S3 buffer transfers sequentially bypassing generic placeholders natively rendering true percent allocations accurately.

## State Abstraction Layer
The hook file `use-knowledge-request.ts` completely removes manual Axios executions from components minimizing dependency sprawl mapping standard TanStack paradigms directly across the shell infrastructure securely executing 401 un-auth handlers generically preventing regressions.

