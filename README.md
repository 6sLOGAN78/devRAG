# DevRAG 🚀

**DevRAG** is an enterprise-grade Retrieval-Augmented Generation (RAG) platform. It features tenant isolation, role-based access control, distributed rate limiting, and a decoupled architecture designed for scale.

## 🏗 Architecture Overview

The system is split into two primary backend services for strict boundary isolation, accompanied by a modern React frontend.

1. **[Go API Gateway (`/internal`, `/cmd`)](./internal/README.md):** High-concurrency routing, authentication, RBAC, tenant isolation, and MySQL database management.
2. **[Python ML Engine (`/api`, `/rag`, `/deepdoc`)](./api/README.md):** Heavy machine learning workloads, including YOLOv8 vision parsing, semantic chunking, embeddings, hybrid search (BM25 + Dense), and LLM text generation.
3. **[React Frontend (`/web`)](./web/README.md):** Tailwind CSS + React Query Single Page Application (SPA).

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
