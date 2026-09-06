# 01 - Monorepo Setup & Service Boundaries

## Objective
Establish a production-ready monorepo structure that mirrors RAGFlow's dual-engine (Go/Python) architecture. This defines strict boundaries between the Go API, Python ML Workers, and the React Frontend.

## Production Requirements & Boundaries
RAGFlow is not a simple monolithic API. It relies on a high-concurrency Go engine for I/O and routing, and a Python engine for compute-heavy ML tasks.

1. **`internal/` and `cmd/` (Go Engine):**
   - **Role:** High-concurrency REST API, WebSockets (SSE), metadata CRUD, and ingestion orchestration.
   - **Structure:** `cmd/ragflow_server.go` (Entrypoint), `internal/router/`, `internal/handler/`, `internal/service/`, `internal/dao/`.
   - **Constraint:** Go must NEVER execute ML models or OCR directly. It pushes tasks to NATS/Redis.

2. **`api/`, `rag/`, and `deepdoc/` (Python Engine):**
   - **Role:** Quart ASGI API (Port 9380), Task Executors, Layout Analysis, Embedding generation.
   - **Structure:** `api/ragflow_server.py`, `rag/svr/task_executor.py`, `deepdoc/vision/`.
   - **Constraint:** Python should offload simple CRUD to Go where possible to save the GIL for ML workloads.

3. **`web/` (React SPA):**
   - **Role:** User Interface.
   - **Structure:** Vite, React Router 7, Zustand.

## Implementation Tasks
- [ ] Initialize Git repository.
- [ ] Create Go directories (`cmd/`, `internal/handler/`, `internal/service/`, `internal/dao/`) and run `go mod init`.
- [ ] Create Python directories (`api/`, `rag/`, `deepdoc/`, `common/`) and set up Poetry or `requirements.txt`.
- [ ] Create `web/` and initialize a React + TypeScript project.
- [ ] Configure `golangci-lint` (Go), `ruff` (Python), and `eslint` (React) for CI/CD checks.

## Deliverable
A standardized, dual-language monorepo structure ready for production coding.
