# Implemented Features

This file tracks the design and behavior of features implemented by agents in this repository.
## Monorepo Dual-Engine Setup
- Established strict directory boundaries for Go (`internal/`, `cmd/`) and Python (`api/`, `rag/`, `deepdoc/`).
- Scaffolded React SPA frontend in `web/` using Vite.
- Initialized package managers (`go mod`, `npm`, `requirements.txt`) and linter configs (`ruff`, `golangci-lint`).
## Phase 02: Production Infrastructure
- Set up `docker-compose-base.yml` with MySQL 8.0, Valkey 8, NATS 2.10, MinIO, Infinity v0.3.0, and Nginx.
- Configured `.env` variables for credentials, avoiding git commits of secrets.
- Implemented health checks, persistent volumes, and a unified Docker network (`ragflow-network`).
- Created infrastructure test suite validating container startup and health endpoints.
## Phase 03: Unified Configuration Management
- Established single source of truth at `conf/service_conf.yaml` for both Go and Python backends.
- Implemented strict custom env-interpolation to guarantee identical cross-language semantics.
- Implemented `internal/config/config.go` with strict JSON tags and `gopkg.in/yaml.v3` parsing.
- Implemented `common/settings.py` leveraging `pyyaml` and strict `pydantic` structural validation.
- Verified full validation suite including missing fields, type errors, invalid ports, and overrides.
## Phase 04: Core Database Models & Dual-ORM Synchronization
- Defined schema contracts for `Tenant`, `User`, and `UserTenant`.
- Implemented `internal/dao/models.go` with strict GORM annotations.
- Implemented `api/db/db_models.py` matching exactly to the Go schema using Peewee.
- Configured pooled database connections in both Go (`internal/dao/db.go`) and Python (`api/db/connection.py`).
- Added integration test suite to verify cross-language read/write compatibility and strict constraints.
## Phase 02 (Gin): Go Gin HTTP Server
- Initialized Go Gin HTTP server on port 9380.
- Integrated unified configuration system for port provisioning.
- Implemented base CORS, Logging, and Recovery middleware.
- Created `/api/v1/health` base endpoint.
- Verified with unit tests (`go test ./...`) and runtime validation.
## Phase 03 (Quart): Python Quart ASGI Service
- Initialized Python Quart ASGI server on port 9381 using Hypercorn.
- Established `/api/v1/ml` and `/api/v1/agents` blueprints boundaries.
- Integrated base CORS, Logging, and robust Exception handling middlewares.
- Completed runtime verification and passed full `pytest` and `ruff check` pipelines.
## Phase 02-03: Authentication Flow
- Implemented `/api/v1/user/register` handling bcrypt password hashing and MySQL persistence.
- Implemented `/api/v1/user/login` handling JWT generation and Redis session caching.
- Built strictly-coupled `Auth` middleware enforcing signed JWT expiration and correlated Redis `session_id` presence.
- Updated unified configuration contracts across Go and Python to load `Auth` secrets implicitly.
## Phase 02-04: Tenant Context & Cross-Stack Authentication
- Expanded Go Auth middleware to strictly enforce `UserTenant` DB relationship validation and inject secure `tenant_id` context.
- Implemented `/api/v1/user/info` exposing safe user context output natively in Go.
- Recreated identical auth/tenant evaluation rules as an async `@require_auth` decorator for Python Quart bridging `g.user_id` and `g.tenant_id`.
- Proven strict isolation ensuring unowned `X-Tenant-ID` injections gracefully reject with 403 Forbidden.
## Phase 02-05: Multi-Tenant Context & RBAC Foundation
- Modified `ResolveTenantContext` in Go to correctly parse and extract `role` natively exposing `c.GetString("role")`.
- Updated `auth_decorator.py` in Python Quart stack to extract and bind `g.role` across endpoints dynamically.
- Deployed active prevention logic securing systems against `invite` states impersonating valid user contexts (403 Forbidden).
- Completed and wrote extensive documentation detailing RBAC integration parameters for upcoming CRUD schemas.
## Phase 03-01: Dataset CRUD API
- Implemented `Dataset` models matching RAG standards across both Go and Python Peewee abstractions.
- Created `internal/dao/dataset.go` exclusively bounding retrieval and deletion scopes against authenticated `tenant_id` clauses to eliminate IDOR vectors.
- Developed `internal/service/dataset.go` generating IDs correctly assigning `tenant_id`, `created_by`, and initialized states cleanly.
- Exposed `POST /api/v1/dataset`, `GET /api/v1/dataset/list`, and `DELETE /api/v1/dataset/:id` securely over HTTP enforcing isolation contexts.
## Phase 03-02: Document Upload API
- Implemented `Document` models across Go and Python Peewee mapping raw MinIO locations.
- Constructed `internal/storage/minio.go` abstracting MinIO storage operations (PutObject, GetObject, DeleteObject).
- Engineered `internal/service/document.go` generating secure, traversal-resistant MinIO keys: `tenant/{tenant_id}/dataset/{dataset_id}/document/{document_id}/original`.
- Validated Dataset ownership comprehensively preventing cross-tenant document injections into unowned Datasets.
- Deployed Multipart upload endpoint `POST /api/v1/document/upload` rejecting uploads > 50MB.
## Phase 04: Deep Document Parsing (DeepDoc)
- Integrated PyTorch, PaddleOCR, YOLOv8 into the environment.
- Configured DeepDoc parser logic for text and markdown files.
- Implemented `GeneralChunker` yielding strictly formatted `DocumentChunk` models supporting NLP token limits.

## Phase 05: Ingestion Pipeline & Task Synchronization
- **Task Queue Models**: Implemented `DocumentTask` and `DocumentChunk` schemas mirroring the Go struct/Python Peewee structure to track asynchronous jobs.
- **Go Syncer Worker**: Created background Go daemon pulling unstarted tasks securely utilizing MySQL `SELECT ... FOR UPDATE SKIP LOCKED` logic and dispatching them via internal HTTP POST calls to Python.
- **Python Task Executor**: Implemented an async `POST /api/v1/ml/parse_document` Quart endpoint that offloads work via `run_in_executor` to avoid loop-blocking. Downloads from MinIO, parses chunks with DeepDoc, and inserts idempotently via Peewee.
- **Redis Concurrency**: Developed `RedisDistributedLock` context manager (`common/redis_conn.py`) implementing distributed mutual exclusion with Lua release semantics. Integrated into progress updates and cleanup loops to protect against multi-worker race conditions.
- **Frontend Progress UI**: Connected the authoritative backend task processing system into the React interface. Added a robust React Query polling mechanism pulling from a new batched Go `GET /api/v1/document/status` API mapping exact percentage metrics into the Datasets UI view.
