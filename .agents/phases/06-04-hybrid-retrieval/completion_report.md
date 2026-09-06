# Phase 06-04 Hybrid Retrieval Implementation Report

## 1. What changed
* Updated `BaseVectorStore` to define `search_lexical` alongside `search` (dense).
* Updated `InfinityAdapter` to initialize full-text indices alongside dense vector indices when `create_index` is called.
* Implemented `InfinityAdapter.search_lexical` using Infinity's native `match_text` API.
* Created `rag/nlp/retrieval.py` which provides a `RetrievalService`.
* `RetrievalService` concurrently executes Dense (semantic KNN via `EmbeddingEngine`) and Lexical (BM25 via FTS) queries and performs deterministic RRF fusion.

## 2. Files changed
* `rag/vector_store/base.py`
  * Responsibility: Interface definition for vector backends.
  * Reason: Added `search_lexical` to explicitly separate lexical queries from dense queries.
* `rag/vector_store/infinity_adapter.py`
  * Responsibility: Infinity database operations.
  * Reason: Hooked up Infinity's native `IndexType.FullText` and implemented `search_lexical` using `match_text()`.
* `rag/nlp/retrieval.py`
  * Responsibility: Hybrid ranking service.
  * Reason: New file to coordinate concurrent fetching of dense + lexical candidates and computing fused reciprocal ranks before returning the `top_k` results.
* `tests/unit/test_retrieval.py`
  * Responsibility: Unit testing suite for retrieval service.
  * Reason: New tests for fusion mathematics, failure modes, deduplication, and tie-breaking determinism.

## 3. Architecture
```text
                  User Query
                      |
        +-------------+-------------+
        | (Thread 1)                | (Thread 2)
        v                           v
  EmbeddingEngine           Infinity search_lexical
        |                           |
        v                           v
 Infinity search (dense)            |
        |                           |
        +-------------+-------------+
                      |
                      v
             Result Deduplication
                      |
                      v
             Reciprocal Rank Fusion (RRF)
                      |
                      v
                Ranked Chunks
```

## 4. Fusion strategy
* **Algorithm**: Reciprocal Rank Fusion (RRF) 
* **Formula**: `chunk.score += 1 / (rrf_k + rank_i)` for each backend `i` where the chunk is present.
* **Parameters**: Default `rrf_k = 60`, which is standard for search scaling.
* **Candidate Sizing**: Fetches `top_k * 3` candidates independently from both dense and lexical pipelines before truncation to ensure high-recall fusion.
* **Tie-Breaking**: If RRF scores collide, sorting falls back deterministically to: Lexical Rank Ascending, Dense Rank Ascending, then Chunk ID Ascending.

## 5. Backend behavior
* **Infinity (Supported & Configured)**: `create_index` was updated to initialize `IndexType.FullText` on the `content` field. `search_lexical` leverages native `match_text()`. This avoids the need for a completely separate Elasticsearch backend cluster because Infinity handles both natively.
* **Fallback Behavior**: If the lexical query throws an exception (e.g. FTS index absent on older data, or backend lacks FTS), the exception is suppressed with a warning, and retrieval gracefully degrades to dense-only candidates. If dense search fails, the entire task bubbles up the error because semantic search is mandatory.

## 6. Filtering/security
All requests passed down to `BaseVectorStore.search` and `BaseVectorStore.search_lexical` propagate identical `filters` arguments directly to the database SQL-like conditions. By embedding the `dataset_id` into the index name (`idx_{dataset_id}`), Infinity natively enforces multi-tenant boundary containment at the table level.

## 7. Failure behavior
* **Embedding failure**: The dense search thread will raise an exception, terminating the query. 
* **Vector DB dense failure**: Aborts the query cleanly.
* **Vector DB lexical failure**: Prints a warning and falls back to semantic dense results only.
* **Empty results**: Cleanly returns an empty array.

## 8. Tests
Tests executed successfully:
* `test_empty_query`: Verified empty strings yield zero results without calling LLM embeddings.
* `test_rrf_and_deduplication`: Manually proved RRF scores align with exact theoretical math and chunk deduplication rules.
* `test_tie_breaking`: Verified perfectly tied scores fall back predictably to lexical rank and stable IDs.
* `test_hybrid_search_flow`: Validated that `ThreadPoolExecutor` correctly submits queries to both backends.
* `test_lexical_fallback_gracefully`: Verified FTS crashes don't bring down the semantic results.
* `test_dense_failure_bubbles_up`: Proved mandatory dense failures crash properly.

## 9. Known limitations
* The older Infinity Python SDK (`0.3.0`) currently omits precise inner-scoring behavior for `match_dense` due to planner constraints (`SCORE()` not valid except in `match_text` in this version). RRF successfully sidesteps this by relying only on returned ranking order, completely bypassing the need for raw backend scores.

## 10. 06-05 Readiness
The `RetrievedChunk` model encapsulates:
* `content`
* `chunk_id`, `document_id`, `dataset_id`
* `dense_score`, `lexical_score`, `dense_rank`, `lexical_rank`
* `score` (the fused RRF score)
* `retrieval_method` ("dense", "lexical", or "hybrid")
This strongly-typed dataclass provides everything a cross-encoder requires for full context payload and query formulation in the upcoming `06-05-reranking-engine` phase.
