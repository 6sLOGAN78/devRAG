# Phase 06: Core RAG & Vector Engine

## Phase Objective
Implement the Vector Database integration, Embedding generation, and Hybrid Retrieval (Dense + BM25 + Rerank) algorithms.

## Why This Phase Comes Here
Chunks exist in the relational DB. To search them, they must be embedded and indexed in a Vector DB.

## Dependencies
Depends on:
- Phase 05 (Ingestion generates chunks)

Required by:
- Phase 07 (Agent workflow requires retrieval)

## Phase Architecture
Python RAG module integrates with LiteLLM for embeddings, and interfaces with VectorDBs (Infinity/Elasticsearch). Includes cross-encoder reranking.

## Subphase Order
01-vector-db-adapters -> 02-embedding-models -> 03-indexing-pipeline -> 04-hybrid-retrieval -> 05-reranking-engine

## Phase Deliverable
A complete search engine capable of receiving a query, finding relevant chunks using hybrid search, and reranking them.

## Phase Definition of Done
- Chunks are successfully vectorized and indexed.
- Querying the engine returns highly relevant chunks.
- Hybrid search (BM25 + Vector) works.

## What NOT To Build Yet
LLM generation (done in Phase 07).

## Next Phase
Phase 07: Agentic Workflow Engine (Backend)

## Distributed Coordination Requirements
- **GraphRAG Indexing**: Must use `RedisDistributedLock(f"graphrag_task_{kb_id}")` to prevent concurrent writes/merges to the same Knowledge Base.
- **Document Store**: Must use `RedisDistributedLock(lock_name)` in `ob_conn_base.py` to prevent concurrent initialization and writes.