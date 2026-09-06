# DevRAG Fidelity Audit

## Architecture Overview
- Go Gateway API -> MySQL -> Syncer -> Python ML API -> Vector DB (Infinity).

## Identified Discrepancies
### 1. Ingestion Task Creation
- **RAGFlow Behavior**: When a document is uploaded, an entry is created in the `document` table and concurrently one or more entries are created in the `task` table. An async queue polls tasks.
- **DevRAG Baseline**: The Go API `UploadDocument` created the `Document` record in MySQL, but failed to create a `DocumentTask` record. The `Syncer` polled for `unstart` tasks but found none, causing the ingestion pipeline to hang indefinitely at `pending`.
