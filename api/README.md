# Python Machine Learning Engine (`/api`)

This directory houses the Python-based AI and Machine Learning engine for **DevRAG**. 
While the Go Gateway handles high-concurrency client requests, this Python service processes the heavy AI operations synchronously and asynchronously via Quart/Hypercorn.

## Key Responsibilities

- **Document Orchestration:** Interfaces with the `deepdoc` parsing pipelines for complex file extraction.
- **RAG Generation:** Orchestrates hybrid search logic (BM25 + Dense) via the Infinity vector database.
- **LLM Proxying:** Directly proxies generation requests from the Go gateway to external/tenant-configured LLMs via `litellm`.
- **Worker Execution:** Listens for asynchronous jobs triggered by Go tasks.

## Starting the Service

```bash
# From the root directory:
source venv/bin/activate
export PYTHONPATH=.
python api/ragflow_server.py
```
