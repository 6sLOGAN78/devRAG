# Master Implementation Overview

## Project Goal
To build an enterprise-grade, dual-stack Retrieval-Augmented Generation (RAG) platform, matching the scope and capabilities of RAGFlow. The system features a visual agent workflow builder, deep document understanding (vision-based OCR and layout recognition), and a highly concurrent gateway.

## Final Architecture
- **Frontend**: React 18 SPA, Tailwind, Zustand, React Flow (Canvas).
- **Gateway & High-Concurrency Backend**: Go (Gin framework). Handles Auth, CRUD, and task synchronization.
- **AI & Agent Backend**: Python (Quart ASGI). Handles ML processing, embeddings, LLM orchestration, and graph execution.
- **DeepDoc Engine**: Python (PyTorch/PaddleOCR/YOLOv8) for layout-aware document chunking.
- **Storage**: MySQL (Metadata), Redis (Cache/Session/Locks), MinIO (Object Storage), Vector DB (Semantic search).

## Implementation Dependency Graph
```text
Phase 01 (Project Foundation & Infrastructure)
   ↓
Phase 02 (Gateway & Authentication)
   ↓
Phase 03 (Knowledge Base & Document Management)
   ↓
Phase 04 (Deep Document Parsing)
   ↓
Phase 05 (Ingestion Pipeline & Task Sync)
   ↓
Phase 06 (Core RAG & Vector Engine)
   ↓
Phase 07 (Agentic Workflow Engine - Backend)
   ↓
Phase 08 (Agent Canvas UI - Frontend)
   ↓
Phase 09 (Chat Playground & Streaming API)   <--- MVP ACHIEVED
   ↓
Phase 10 (Production Hardening & Scalability)
```

## Phase Index
- [Phase 01: Project Foundation & Infrastructure](phase-01-project-foundation/README.md)
- [Phase 02: Gateway & Authentication](phase-02-gateway-and-auth/README.md)
- [Phase 03: Knowledge Base & Document Management](phase-03-knowledge-base/README.md)
- [Phase 04: Deep Document Parsing (DeepDoc)](phase-04-deepdoc-parsing/README.md)
- [Phase 05: Ingestion Pipeline & Task Synchronization](phase-05-ingestion-pipeline/README.md)
- [Phase 06: Core RAG & Vector Engine](phase-06-core-rag-vector/README.md)
- [Phase 07: Agentic Workflow Engine (Backend)](phase-07-agent-engine-backend/README.md)
- [Phase 08: Agent Canvas UI (Frontend)](phase-08-agent-canvas-ui/README.md)
- [Phase 09: Chat Playground & Streaming API](phase-09-chat-and-streaming/README.md)
- [Phase 10: Production Hardening & Scalability](phase-10-production-hardening/README.md)

## Milestones
1. **Infrastructure Up**: Phase 01
2. **Gateway Secured**: Phase 02
3. **Data Ingestion Active**: Phase 05
4. **Agent Logic Live**: Phase 07
5. **MVP Complete**: Phase 09

## MVP
**MVP is achieved at the end of Phase 09.**
MVP Includes:
- User Auth & Tenant isolation.
- Uploading complex PDFs to MinIO.
- DeepDoc parsing (OCR + Layout) via async workers.
- Vector indexing & Hybrid Retrieval.
- Visual Agent Canvas creation.
- Streaming Chat UI with Citation highlighting.

MVP Excludes:
- Admin Dashboards (Phase 10)
- Advanced Rate Limiting (Phase 10)
- Kubernetes Deployment (Phase 10)

## Production Ready
The system is considered production-ready at the end of **Phase 10**, once rate limits, integration tests, and Kubernetes manifests are established.

- **Distributed Coordination:** `RedisDistributedLock` (via `common/redis_conn.py`) is used across the Python backend for synchronizing concurrent background operations and avoiding race conditions across instances.