# devRAG Architecture & Vibe

You are an expert full-stack developer working on **devRAG**, a multi-tenant enterprise RAG (Retrieval-Augmented Generation) system. 

## Core Stack
- **Edge / Ingress:** Nginx
- **Backend (High Concurrency & Ingestion):** Go (located in `internal/`)
- **Backend (AI/ML & API):** Python Quart/Flask (located in `api/`)
- **Databases:** 
  - Relational: MySQL (stores metadata, users, config)
  - Vector/Search: Infinity / Elasticsearch (stores embeddings)
  - Cache/Queue: Valkey/Redis, NATS JetStream
  - Storage: MinIO / S3

## Global Architectural Rules
1. **Separation of Concerns:** 
   - Never write raw SQL in handlers. Always strictly follow the **Handler -> Service -> DAO** layered pattern.
2. **Multi-Tenancy is Mandatory:** 
   - Almost every database table (e.g., Knowledgebase, Document, Dialog) has a `tenant_id`. 
   - When querying the database or vector store, you MUST always filter by `tenant_id` to prevent cross-tenant data leaks.
3. **Language Boundaries:** 
   - Use Python for heavy ML tasks, embedding generation, and LLM integrations.
   - Use Go for high-throughput CRUD APIs, document parsing queues, and worker execution.
4. **Agent Behavior:**
   - Always think step-by-step.
   - Before making changes, ensure you understand the dependencies between the Go and Python services.
5. **Continuous Documentation & Verification:**
   - At the conclusion of EVERY task or feature implementation requested by the user, you MUST:
     1. Automatically update `README.md` and `implementation.md` in the repository root.
     2. Update the `.agents/features.md` file to track the design and behavior of the newly implemented feature.
     3. Perform a repository-wide scan to find and fix any bugs or edge cases related to the feature you just implemented (using the `.agents/rules/bug-and-issue.md` prompt).
