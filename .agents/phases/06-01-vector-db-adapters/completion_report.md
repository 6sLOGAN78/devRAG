# Phase 06-01 Vector DB Adapters Implementation Report

## Architecture Discovered
- **Vector-store architecture**: No prior vector database abstractions were present. The infrastructure uses Infinity v0.3.0 as configured in `docker-compose-base.yml` and `conf/service_conf.yaml`.
- **Elasticsearch integration**: Absent from the repository configuration, so `ElasticsearchAdapter` was deliberately omitted to avoid unsupported dead code.
- **Infinity integration**: Present in config. Requires `infinity-sdk`.
- **Dataset/KB lifecycle**: Handled purely in Go (`internal/service/dataset.go`). Index creation will be handled idempotently from the Python embedding worker upon first chunk insertion.
- **Document-store architecture**: `ob_conn_base.py` was missing, so a foundational `DocumentStoreBase` abstraction was created in `rag/utils/ob_conn_base.py`.
- **GraphRAG architecture**: A stub was created in `rag/graphrag/index.py` to establish the required distributed lock patterns ahead of the full GraphRAG implementation.
- **Redis architecture**: `RedisDistributedLock` exists in `common/redis_conn.py` and correctly utilizes atomic `SETNX` + Lua deletion.

## Adapter Contract
Implemented in `rag/vector_store/base.py`:
- `BaseVectorStore`: Abstract base class.
- `VectorRecord`: Domain representation of an indexable chunk (id, document_id, dataset_id, content, embedding, metadata).
- `SearchResult`: Domain representation of a retrieved chunk.
- **Methods**:
  - `create_index(index_name, dimensions)`: Idempotently creates the backend schema.
  - `delete_index(index_name)`: Drops the index.
  - `bulk_insert(index_name, records)`: Efficiently batches dictionary conversions for insertion.
  - `search(index_name, query_vector, top_k, filters)`: Translates domain filters and executes dense vector similarity mapping to `SearchResult`.
  - `delete(index_name, document_id)`: Removes vectors by document scope.
  - `health_check()`: Verifies connectivity.

## Backend Implementations
### InfinityAdapter
- **Files**: `rag/vector_store/infinity_adapter.py`
- **Client**: `infinity-sdk` using `infinity.connect()`.
- **Configuration**: Uses `cfg.infinity.host` and `port` from `common.settings.py`.
- **Schema**: Rigidly mapped to `varchar` for IDs and `vector, {dimensions}, float` for embeddings.
- **Index mapping**: Defaults to `Hnsw` index with `cosine` metric, `M=16`, `ef_construction=200`.
- **Search implementation**: Utilizes `match_dense` mapped into Polars DataFrame via `to_pl()`, strictly abstracted from the RAG caller.
- **Limitations**: Infinity SDK relies on Polars. Specific Polars versions (`polars==1.2.1`) are enforced to avoid Infinity internal import breakages (`null_count_dtype`).

## Dataset → Index Flow
```text
Dataset Created (Go API)
 ↓
Document Uploaded & Parsed (Phase 05)
 ↓
Python Embedding Worker (Next Phase)
 ↓
BaseVectorStore.create_index(dataset_id, dimensions) [Idempotent]
 ↓
BaseVectorStore.bulk_insert(...)
```

## Distributed Coordination
### GraphRAG
- `rag/graphrag/index.py` utilizes `RedisDistributedLock(f"graphrag_task_{kb_id}")`.
- **Critical section**: Wrap only the stateful `_merge_graph_state` mutation block. Time-intensive LLM extraction occurs outside the lock to minimize contention.

### Document Store
- `rag/utils/ob_conn_base.py` (`DocumentStoreBase`) utilizes `RedisDistributedLock(f"doc_store_{kb_id}")`.
- **Critical section**: Protects `initialize()` and `write()` boundaries simulating safe state machine mutations of knowledge base structures.

## Tests
- **Unit/Contract Tests**: Created `tests/unit/test_vector_store.py` passing seamlessly.
- **Mock Integration**: Validated `InfinityAdapter` request construction, method chaining, and schema parsing entirely through `unittest.mock`.
- **Distributed Locks**: Tested acquisition and release mapping for both Document Store and GraphRAG wrappers.
- **Polars Stability**: Tested Infinity import pipeline bypassing known `polars-lts-cpu` incompatibilities.

## Files Changed
- `requirements.txt` (Added `infinity-sdk`, `polars==1.2.1`)
- `rag/vector_store/base.py` (Created)
- `rag/vector_store/infinity_adapter.py` (Created)
- `rag/utils/ob_conn_base.py` (Created)
- `rag/graphrag/index.py` (Created)
- `tests/unit/test_vector_store.py` (Created)

## `.agents`
- No `.agents` guidelines modified as domain contracts logically fulfilled requested abstractions natively.

## Known Limitations
- The Infinity SDK is tightly coupled to Polars, which occasionally creates cross-library resolution conflicts (requiring exact pinning).
- Without actual embedding models running yet, the dense match parameters (`top_k`, `cosine`) remain fixed to standard defaults.

## Next Subphase
02-embedding-models
