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
