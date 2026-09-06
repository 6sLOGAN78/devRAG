# Fidelity Gaps

## Resolved Gaps
1. **[P0] Ingestion Task Creation Bug**
   - *Issue*: `UploadDocument` failed to create `DocumentTask` records in MySQL, halting the entire indexing pipeline permanently.
   - *Fix*: Modified `internal/dao/document.go` to include `CreateDocumentWithTask` which executes a transactional insert of both `Document` and `DocumentTask`. Modified `internal/service/document.go` to use this new function.
   - *Status*: Verified. Tasks are now successfully claimed by the Syncer and dispatched to the Python ML worker.

## Unresolved Gaps
*(Will populate as inspection continues)*
