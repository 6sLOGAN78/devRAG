# Phase 03 Indexing Pipeline Implementation Report

## Architecture Discovered
* **Actual Phase 05 parsing flow**: `parsing_service.py` executes synchronously via `loop.run_in_executor` to parse, chunk, and save chunks transactionally to MySQL.
* **Actual chunk persistence flow**: MySQL chunks are batch-inserted via `DocumentChunk.insert_many`. The entire block was wrapped in a transaction, failing the task if aborted.
* **Actual embedding architecture**: `06-02 EmbeddingEngine` provides stable batched conversions.
* **Actual vector-store architecture**: `06-01 VectorStore` connects to `Infinity` via `InfinityAdapter`.
* **Actual indexing insertion point**: Indexing was injected immediately after MySQL chunk persistence but before task status is marked `success` in `parsing_service.py`. This groups the ingestion path under a single task state, simplifying retry and recovery models.

## Data Flow
The real call chain for indexing is now:
```text
DocumentTask processing
 ↓
Chunk Generation (deepdoc)
 ↓
DocumentChunk saved to MySQL
 ↓
IndexingService.index_document(chunks)
 ↓
EmbeddingEngine.embed(texts)
 ↓
VectorRecord[] generated
 ↓
InfinityAdapter.bulk_insert()
 ↓
Vector DB (Infinity)
 ↓
DocumentTask marked SUCCESS
```

## Consistency Model
* **MySQL transaction boundary**: MySQL chunks are inserted as a batch. 
* **Vector DB transaction/operation boundary**: Infinity bulk_insert handles vectors concurrently.
* **Cross-system consistency model**: The system provides **eventual consistency with idempotent retry recovery**. 
  - If MySQL insertion succeeds but Vector DB fails, the exception propagates, marking the task as `failed`. The chunks remain in MySQL, but the vector DB has no chunks.
  - Upon retry, the task idempotently deletes existing chunks in MySQL and existing vectors in VectorDB for this `document_id`, starting fresh.
* **Idempotency mechanism**: 
  - `DocumentChunk.delete().where(document_id).execute()`
  - `vector_store.delete(index_name, document_id)`
  Both are explicitly invoked before insertion.
* **Reprocessing behavior**: Reprocessing a document deletes stale vectors because `document_id` is passed to the deletion routines.

## Embedding
* **model**: `all-MiniLM-L6-v2` (configured dynamically as a default in `IndexingService`)
* **provider**: `huggingface`
* **dimension**: `384`
* **batch size**: `100`
* **retry behavior**: Tenacity traps errors from remote LLMs inside the `EmbeddingEngine` (configured in 06-02).

## Vector Store
* **backend**: Infinity (`infinity-sdk==0.3.0`)
* **index**: `idx_{dataset_id}` (dashes replaced with underscores for valid identifiers)
* **vector ID**: `chunk.id` - 1:1 mapped to the exact UUID of the chunk in MySQL.
* **metadata**: Left extensible for future subphases.
* **bulk operation**: Uses `table.insert(data)` for batch inserts.
* **error behavior**: If a batch insertion fails, an exception is thrown and the task fails.

## Redis
* **update_progress**: The existing `RedisDistributedLock("update_progress")` lock is correctly preserved when marking the task `success` or `failed`.
* **graphrag**: (Not touched in this phase as chunks are independently processed).

## Files Changed
* `api/services/parsing_service.py` (Modified to invoke `IndexingService` inside the worker loop)
* `api/services/indexing_service.py` (Created)
* `tests/unit/test_indexing_service.py` (Created unit tests)
* `rag/vector_store/infinity_adapter.py` (Fixed Infinity connection arguments and dropped unsupported `SCORE()` in dense matching for Infinity `0.3.0`)
* `test_infinity_live.py` (Created integration/E2E search validation)

## Tests
* **Unit tests**: `test_indexing_service.py` mocks Infinity and verifies batch mapping, embedding logic, dimension limits, and idempotency logic. 3 tests passing.
* **Idempotency tests**: The mock successfully validates that `vector_store.delete` runs before `embed`.
* **Failure-injection tests**: Demonstrated in the idempotency test that if `delete` raises a warning (e.g., table doesn't exist yet), the index still proceeds gracefully.
* **E2E ingestion / Search verification**: Ran a live `test_infinity_live.py` validating that a chunk can be embedded and successfully searched via `match_dense()` inside Infinity in Docker.

## Known Limitations
* **Infinity 0.3.0 limitations**: The dense search query currently disables `_score` output because Infinity 0.3.0's planner throws an error if `SCORE()` is used outside fusion or text/tensor matches on this version. This will be natively restored in `06-04 hybrid-retrieval` when the fusion backend is wired.
* **Sync Blocking**: Indexing occurs synchronously within the python executor thread pool. This is appropriate for current concurrency boundaries but could bottleneck large files if embeddings are excessively slow.
