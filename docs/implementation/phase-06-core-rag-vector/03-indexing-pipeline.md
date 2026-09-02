## Objective
Connect the parsing task executor (Phase 05) to the Embedding and Vector DB adapters.

## Why Now?
Close the ingestion loop: Parse -> Chunk -> Embed -> Index.

## Dependencies
- 02-embedding-models
- Phase 05 Task Executor

## Implementation Tasks
- [ ] Update Python Task Executor (`parsing_service.py`).
- [ ] After saving chunks to MySQL, batch process them through `EmbeddingEngine`.
- [ ] Insert vectorized chunks + metadata into `VectorStore`.
- [ ] Ensure transaction consistency (if DB insertion fails, rollback).

## Components
- Indexing Pipeline

## Files
- `api/services/parsing_service.py`

## Interfaces
N/A

## Data Changes
Inserts data into Vector DB.

## Data Flow
Chunks -> Embeddings -> VectorDB Index

## Testing
- End-to-end ingestion test: Upload PDF -> Check MySQL chunks -> Check VectorDB index.

## Deliverable
Complete ingestion pipeline to Vector DB.

## Definition of Done
- Uploaded documents are automatically fully indexed and searchable.

## Next Subphase
04-hybrid-retrieval