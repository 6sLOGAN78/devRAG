# Fidelity Gaps

## Resolved Gaps
1. **[P0] Ingestion Task Creation Bug**
   - *Issue*: `UploadDocument` failed to create `DocumentTask` records in MySQL, halting the entire indexing pipeline permanently.
   - *Fix*: Modified `internal/dao/document.go` to include `CreateDocumentWithTask` which executes a transactional insert of both `Document` and `DocumentTask`. Modified `internal/service/document.go` to use this new function.
   - *Status*: Verified. Tasks are now successfully claimed by the Syncer and dispatched to the Python ML worker.

## Unresolved Gaps
*(Will populate as inspection continues)*
2. **[P1] Storage Bucket Discrepancy**
   - *Issue*: The Go API (`internal/storage/minio.go`) uploads all documents to a hardcoded `devrag-documents` bucket. The Python `parsing_service.py` incorrectly assumed the first path segment was the bucket name (e.g., `tenant`), causing MinIO `NoSuchBucket` errors during task execution.
   - *Fix*: Patched `api/services/parsing_service.py` to correctly expect the `devrag-documents` bucket and pass the full `minio_path` as the object name.
   - *Status*: Verified. Python worker successfully downloads from MinIO, parses, and inserts chunks into Infinity.
