# devRAG ↔ RAGFlow Parity Audit

## 1. Executive Summary
This document presents the findings of a comprehensive, repository-wide parity audit of the devRAG implementation against the official RAGFlow reference documentation. The objective is to identify deviations in architecture, data models, APIs, and functional capabilities without modifying the codebase. 

Overall, devRAG establishes a clean, testable baseline with strong authentication, RBAC, and basic Dataset/Document CRUD operations. However, it exhibits **significant architectural and schema deviations** compared to the mature RAGFlow reference implementation. Specifically, devRAG consolidates functionalities into the Go gateway that RAGFlow assigns to Python, and relies on vastly simplified database schemas. Major capabilities such as chunking, embedding, vector search, LLM integration, and agents are currently missing in devRAG.

## 2. Audit Scope
- Reference Docs: `/home/logan78/Desktop/devRAG/ragflow-docs`
- devRAG Codebase: `/home/logan78/Desktop/devRAG`
- Covered Areas: Architecture, Backend/Frontend APIs, Data Models, Document Ingestion, Auth/RBAC, Infrastructure.

## 3. Reference Documentation Inventory
A recursive scan of `ragflow-docs/` found 218 Markdown files spanning 25 categories, including:
- **03-backend**: API layers, services, middleware
- **04-api**: REST API endpoint specs
- **05-rag-pipeline**: End-to-end RAG workflows
- **06-document-processing**: Chunking, parsing, OCR, table extraction
- **07-retrieval**: Hybrid search, reranking, filters
- **08-database**: Peewee ORM models and schema specifications
- **11-llm & 12-chat**: Agent integrations and streaming interfaces
- **16-auth**: Tenant isolation and multi-role RBAC

## 4. devRAG Codebase Inventory
A scan of devRAG revealed:
- **`internal/`**: Go Gin gateway managing Authentication (Phase 02), Tenant/RBAC middlewares, and Dataset/Document CRUD operations (Phase 03).
- **`api/`**: Quart ASGI Python backend stub with corresponding Peewee models.
- **`web/`**: React 19 frontend utilizing React Router 7, Tailwind v4, Zustand, and TanStack React Query for dataset/document management.
- **Infrastructure**: MinIO implementation for `Document` uploads, alongside MySQL.

## 5. Overall Parity Score
**Overall Assessment:** EARLY IMPLEMENTATION / MAJOR GAPS
- **Architecture**: DIFFERENT IMPLEMENTATION (Go heavily utilized over Python)
- **Backend**: PARTIAL
- **Frontend**: PARTIAL
- **Database**: DIFFERENT
- **Authentication/RBAC**: MATCH
- **Document ingestion**: EARLY IMPLEMENTATION (Upload only)
- **RAG / Agents**: MISSING
- **Testing**: PARTIAL

## 6. Architecture Comparison
**RAGFlow Reference:** 
- Routes `/api/v1/auth`, `/v1/user`, `/v1/tenant` to **Go**. 
- Routes `/api/v1/datasets`, `/api/v1/agents`, and `/api/v1/chat` to **Python**.

**devRAG Implementation:**
- Routes `/api/v1/dataset` and `/api/v1/document` to **Go**.
- **Difference**: devRAG handles Knowledge Base (Dataset) and Document CRUD via the Go gateway rather than delegating it to the Python ASGI server.
- **Severity**: HIGH (Architectural deviation)

## 7. Service/Component Comparison
- Go Gateway: Implemented.
- Python API: Implemented (Stubbed).
- Task Workers / Celery: **MISSING** (No async processing workers implemented for document parsing).
- Document Parsers (OCR, PDF processing): **MISSING**.

## 8. Database/Data Model Comparison
**Dataset vs Knowledgebase**
- RAGFlow uses `knowledgebase` (`kb_id`, `avatar`, `embd_id`, `parser_id`, `parser_config`).
- devRAG uses `dataset` (`name`, `description`). It entirely lacks embedding and parser configuration fields.
- **Severity**: HIGH.

**Document Model**
- RAGFlow `document` tracks `token_num`, `chunk_num`, `process_duration`, `content_hash`, `parser_id`, `progress`.
- devRAG `document` tracks only `minio_path`, `size`, `type`, `parse_status`.
- **Severity**: HIGH.

## 9. Authentication Comparison
- Both utilize token-based authentication (JWT/Redis).
- **Status**: MATCH.

## 10. Multi-Tenant/RBAC Comparison
- RAGFlow uses `UserTenant` mapping to determine `owner`, `admin`, `normal`, `invite`.
- devRAG enforces this strictly in both Go (`c.Set("role")`) and Python (`g.role`).
- **Status**: MATCH. Tenant isolation is correctly enforced at the DAO layer (`WHERE tenant_id = ?`).

## 11. API Comparison
- RAGFlow `POST /api/v1/datasets` operates in Python.
- devRAG `POST /api/v1/dataset` operates in Go.
- **Status**: DIFFERENT ROUTING / SCHEMAS.

## 12. Frontend Comparison
- React workflows for Auth and Dataset management exist.
- RAGFlow defines a much larger scope (Chat, Workflows, Agents). devRAG has placeholder routes for these.
- **Status**: PARTIAL.

## 13. Document Ingestion Comparison
- RAGFlow encompasses Upload → Parse → Clean → Chunk → Embed → Index.
- devRAG encompasses Upload → Storage (MinIO) → DB Record.
- **Status**: EARLY IMPLEMENTATION.

## 14. Storage Comparison
- MinIO integration is implemented correctly, isolating paths using `tenant/{tenant_id}/dataset/{dataset_id}/document/{document_id}/original`.
- **Status**: MATCH.

## 15. Parsing Comparison
- **Status**: MISSING.

## 16. Chunking Comparison
- **Status**: MISSING.

## 17. Embedding Comparison
- **Status**: MISSING.

## 18. Search/Vector/Retrieval Comparison
- **Status**: MISSING. Infinity/Elasticsearch not yet integrated into code.

## 19. RAG Pipeline Comparison
- **Status**: MISSING.

## 20. Agent/Chat Comparison
- **Status**: MISSING.

## 21. Infrastructure Comparison
- Docker setup handles MinIO, MySQL, and Nginx. 
- Unknown if complete vector DB infrastructure is configured identically.

## 22. Configuration Comparison
- RAGFlow relies heavily on model/LLM configs. devRAG lacks LLM configuration models.

## 23. Async/Worker Comparison
- RAGFlow utilizes complex async queues for document processing.
- devRAG lacks asynchronous parsing workers.
- **Status**: MISSING.

## 24. Observability Comparison
- Loggers exist in devRAG, but advanced code tracing (as per docs `22-code-tracing`) is absent.

## 25. Testing Comparison
- devRAG contains solid unit/integration tests for current functionalities (e.g., `vitest` for React, Go test suites).
- RAGFlow's full e2e scope is missing.

## 26. Critical Differences
| Severity | Area | RAGFlow Reference | devRAG | Difference | Impact | Evidence |
|---|---|---|---|---|---|---|
| CRITICAL | Routing Architecture | `/datasets` routed to Python | `/dataset` routed to Go | Go handles AI entity CRUD | Breaches strict RAGFlow API boundary | `ragflow-docs/apis.md` vs `internal/router/router.go` |
| CRITICAL | Schema Parity | `knowledgebase` and `document` contain extensive parser/LLM configs | Simplified CRUD schema | Missing configuration fields required for Phase 04 | `ragflow-docs/08-database/schema.md` vs `internal/dao/models.go` |

## 27. High-Priority Differences
- **Document Processing Pipeline**: Completely missing in devRAG. Only upload is implemented.
- **Task Worker DB Table**: `task` table missing in devRAG.

## 28. Medium/Low-Priority Differences
- Naming conventions (`Dataset` vs `Knowledgebase`).

## 29. Missing Functionality
- **Feature**: Document Parsing & Chunking.
- **Why it matters**: Required for Vector Indexing.
- **Suggested future phase**: Phase 04.

- **Feature**: Vector Database Integration (Infinity/ES).
- **Feature**: LLM / Chat / Agent completion pipelines.

## 30. Intentionally Different Implementations
- Uses standard REST CRUD conventions in Go (`/api/v1/dataset`) instead of Python. This is functionally equivalent for CRUD but deviates architecturally.

## 31. Extra devRAG Functionality
- None detected that contradict RAGFlow.

## 32. Unknown / Unable to Verify
- NATS JetStream integration specifics are pending async worker implementations.

## 33. Security Findings
- **Tenant Isolation**: EXCELLENT. Tested in Go DAO layers.
- **Cross-tenant access**: Protected.
- **IDOR**: Protected via compound `tenant_id` WHERE clauses.
- **No security vulnerabilities discovered.**

## 34. Recommended Remediation Order
1. **P0**: Align `Dataset` and `Document` data models with RAGFlow's `knowledgebase` and `document` schemas to support parsing configs.
2. **P0**: Decide whether to migrate Dataset/Document APIs back to Python, or formally update RAGFlow architectural plans to accept Go ownership.
3. **P1**: Implement Asynchronous parsing workers and `task` queue table.
4. **P2**: Implement Vector Indexing.

## 35. Complete Traceability Matrix
| Reference Requirement | Reference Evidence | devRAG Implementation | Status | Severity | Notes |
|---|---|---|---|---|---|
| Tenant Isolation | `16-auth/multi-tenant-rbac.md` | `internal/middleware/auth.go` | MATCH | - | Secure. |
| Python Dataset API | `04-api/apis.md` | `internal/handler/dataset.go` | DIFFERENT | CRITICAL | Implemented in Go instead. |
| DB Schema `knowledgebase` | `08-database/schema.md` | `Dataset` ORM Model | PARTIAL | HIGH | Missing LLM/parser config fields. |

## 36. Final Verdict
**PARTIALLY COMPLETE / ARCHITECTURALLY DIVERGENT**

The current devRAG codebase correctly implements the Authentication, RBAC, and Infrastructure layers specified in the initial phases, and accurately enforces tenant isolation. However, it **does not completely reproduce** the RAGFlow reference.

devRAG exhibits a significant architectural deviation by routing AI-entity CRUD APIs (Datasets/Documents) to the Go gateway instead of Python. Furthermore, its database schemas are massively simplified and lack the core parsing, embedding, and tracking fields required to implement the deep document processing pipeline outlined in the RAGFlow reference.
