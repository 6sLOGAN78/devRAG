# Phase 01: Project Foundation

## Phase Objective
Establish the foundational monorepo structure, core infrastructure services (Database, Cache, Queue, Object Storage, Vector DB), and unified configuration management across the dual-stack (Go/Python) backends.

## Why This Phase Comes Here
RAGFlow is a complex, distributed, multi-tenant system. Before writing any API endpoints, the rigid architectural boundaries, dual-language ORM synchronization, and infrastructure orchestrators (Docker Compose) must be fully established and documented.

## Subphase Order
1. **01-monorepo-setup:** File boundaries between Go (`internal/`), Python (`api/`, `rag/`), and React (`web/`).
2. **02-infrastructure-services:** Docker Compose for MySQL, Redis, MinIO, NATS, Infinity.
3. **03-configuration-management:** Unified YAML parsing across languages.
4. **04-database-models:** Peewee (Python) and GORM (Go) models for Multi-Tenancy (Tenant/User).

## Phase Deliverable
A running set of backing services, standard config loaders in both Go and Python, and an empty but structured dual-stack codebase ready for the Gateway & Auth implementation.
