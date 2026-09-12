# DevRAG 🚀

**DevRAG** is a highly-scalable, multi-tenant Retrieval-Augmented Generation (RAG) platform. It seamlessly combines a high-concurrency Go API Gateway with a Python-based Machine Learning Engine to handle document ingestion, layout recognition, vector search, and LLM orchestration at scale.

## ✨ Key Features

- **Robust Multi-Tenancy:** Complete logical isolation for multiple tenants across all services, databases, vector stores, and object stores.
- **Tenant-Owned AI Configuration:** Tenants can securely configure and supply their own LLM and Embedding API keys (OpenAI, Anthropic, Gemini, DeepSeek, etc.) via the TenantLLM service.
- **Advanced Document Parsing (deepdoc):** Built-in support for PDFs, TXT, and Markdown files, leveraging PyMuPDF, OCR (PaddleOCR), and YOLOv8-based layout recognition for complex documents.
- **Flexible Chunking Strategies:** Supports customizable parsing methods configured at the Dataset level (e.g., General Text Chunking, automated Q&A Generation chunking) to optimize retrieval.
- **Hybrid Search Engine:** Powered by [Infinity](https://github.com/infiniflow/infinity), combining Dense Vector search and Keyword/Sparse search (BM25) with cross-encoder reranking.
- **High Concurrency:** Separation of the ML Python workers and the Go Gateway ensures high availability and fast I/O bound routing.

## 🏗 Architecture Overview

The system is split into two primary backend services for strict boundary isolation, accompanied by a modern React frontend.

1. **[Go API Gateway (`/internal`, `/cmd`)](./internal/README.md):** 
   - Handles REST & WebSocket endpoints, routing, authentication, RBAC, tenant isolation, and MySQL database management.
2. **[Python ML Engine (`/api`, `/rag`, `/deepdoc`)](./api/README.md):** 
   - Responsible for heavy machine learning workloads, including YOLOv8 vision parsing, semantic chunking, embeddings, hybrid search, and LLM orchestration.
3. **[React Frontend (`/web`)](./web/README.md):** 
   - A Tailwind CSS + React Query Single Page Application (SPA).

## 📁 Repository Structure

* [**`/api`**](./api/README.md) - Python API and ML background workers
* [**`/cmd`**](./cmd/README.md) - Go application entrypoints
* [**`/internal`**](./internal/README.md) - Go business logic (Handlers, Services, DAOs)
* [**`/web`**](./web/README.md) - React frontend application
* [**`/rag`**](./rag/README.md) - Vector stores, NLP chunking, and LLM orchestration
* [**`/deepdoc`**](./deepdoc/README.md) - Document parsing, OCR, and vision models
* [**`/docker`**](./docker/README.md) - Dockerfiles and local compose environments
* [**`/helm`**](./helm/README.md) - Kubernetes production deployments
* [**`/tests`**](./tests/README.md) - Playwright E2E and Go/Python integration tests

## 🚀 Quick Start (Local Development)

### Prerequisites
- Docker & Docker Compose
- Go 1.22+
- Python 3.10+
- Node.js 18+

### 1. Start Infrastructure
```bash
docker-compose -f docker/docker-compose-base.yml up -d
```
*(Starts MySQL, Redis, MinIO, and Infinity)*

### 2. Run Go Backend
```bash
go run cmd/server/ragflow_server.go -c conf/service_conf.yaml
```

### 3. Run Python ML Backend
```bash
source venv/bin/activate
export PYTHONPATH=.
python api/ragflow_server.py
```

### 4. Run React Frontend
```bash
cd web
npm install
npm run dev
```

The frontend will be accessible at `http://localhost:5173`.

## 🤝 Contributing
Please ensure you run all tests before submitting PRs, maintaining strict tenant boundaries, and following the architecture guidelines where Python handles ML workloads and Go handles high-concurrency infrastructure.
