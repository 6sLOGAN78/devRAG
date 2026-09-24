# RAG Operations (`/rag`)

This directory houses the core Retrieval-Augmented Generation algorithms and integrations for the **DevRAG** Python ML Engine.

## Modules

- **`nlp/embedding.py`**: Resolves Tenant LLM API Keys and executes embedding models (OpenAI, HuggingFace, etc.).
- **`nlp/retrieval.py`**: Coordinates dense and sparse (lexical) search, executing Cross-Encoder reranking to return the most relevant `DocumentChunks`.
- **`vector_store/`**: Abstraction layer for Vector Databases. Currently implemented purely on **Infinity** to support high-performance Hybrid Search (BM25 + Vector).
