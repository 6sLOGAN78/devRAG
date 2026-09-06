# devRAG — Agent Instructions

You are working on **devRAG**, a multi-tenant enterprise RAG system.

## Architecture

* **Go (`internal/`)** — high-concurrency APIs, ingestion, workers, queues.
* **Python (`api/`)** — AI/ML, embeddings, LLM integrations, RAG logic.
* **MySQL** — metadata and relational data.
* **Redis/Valkey** — cache/session state.
* **NATS JetStream** — asynchronous processing.
* **MinIO/S3** — object storage.
* **Infinity/Elasticsearch** — vector/search.
* **Nginx** — ingress.

## Core Rules

1. **Use Handler → Service → DAO/Repository.** No raw SQL in handlers.
2. **Tenant isolation is mandatory.** Tenant-owned database and vector queries must enforce the authenticated `tenant_id`.
3. **Respect language boundaries.** Keep ML/LLM work in Python and high-concurrency/infrastructure work in Go.
4. **Do not silently change architecture.** Record meaningful deviations in `.agents/decisions/`.
5. **Read the relevant `.agents/` phase, architecture, and contract documentation before modifying related code.**

## Superpowers

This repository uses **obra/superpowers** as the engineering workflow.

* Follow applicable Superpowers skills automatically.
* Do not bypass applicable planning, TDD, debugging, review, or verification workflows.
* Do not duplicate Superpowers workflows inside `.agents/`.

**Superpowers defines HOW to work. `.agents/` defines WHAT devRAG must build.**

## Completion

Before declaring work complete:

* Run the relevant tests.
* Verify the implementation against the current phase/feature requirements.
* Update relevant documentation and `.agents/features.md`.
* Record meaningful architectural deviations.
* Report what changed, tests run, and verification status.

Never declare completion when required tests or verification are failing.
Always push with valid commits after each update or anything big you did like something enough to commit.