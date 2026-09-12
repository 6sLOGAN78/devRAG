# RAGFlow to DevRAG Fidelity Audit

## Repository Mapping (High-Level)

### 1. `api/apps/` (REST APIs and WebSockets)
- **RAGFlow:** Contains extensive `_api.py` files (e.g., `agent_api.py`, `chat_api.py`, `chunk_api.py`, `document_api.py`, `file_api.py`).
- **DevRAG:** Migrated to Go under `internal/handler/` for high concurrency (e.g., `agent.go`, `chat.go`, `dataset.go`, `document.go`, `tenant_llm.go`).
- **Status:** *Equivalent but structurally different (Category B).* DevRAG's Go APIs replicate the core endpoints, but lack specific administrative and chunk-level endpoints (e.g., `chunk_api.py`, `search_api.py`).

### 2. `rag/app/` (Document Chunkers/Parsers Configurations)
- **RAGFlow:** Contains `naive.py`, `qa.py`, `resume.py`, `manual.py`, `paper.py`, etc. These files define how documents are chunked based on the user's selected parsing strategy.
- **DevRAG:** Completely missing (Category C: RAGFlow-only). DevRAG only utilizes a generic `GeneralChunker` and has no concept of different parsing methodologies (e.g., QA generation, table logic).

### 3. `deepdoc/parser/` (File Type Parsers)
- **RAGFlow:** `pdf_parser.py`, `excel_parser.py`, `docx_parser.py`, `ppt_parser.py`, `html_parser.py`, etc. (Totaling ~20 parsers).
- **DevRAG:** Only contains `base.py`, `md_parser.py`, and `txt_parser.py`. (Category E: Partial implementation).

### 4. `rag/nlp/` (Retrieval & Embeddings)
- **RAGFlow:** Contains `search.py`, `retrieval.py`, and advanced RAG optimizations.
- **DevRAG:** Implements `embedding.py`, `retrieval.py`, `rerank.py`. DevRAG successfully executes cross-encoder reranking and embedding. (Category A: Equivalent). We recently fixed `TenantLLM` integration for embeddings.

### 5. `api/db/db_models.py` (Database Models)
- **RAGFlow:** Extensive. Contains Models for chunks, plugins, tasks, agents, tenants, API keys, etc.
- **DevRAG:** Subsets these in Go (`internal/dao/models.go`) and Python (`api/db/db_models.py`). 
- **Gap Identified:** `Dataset` in DevRAG previously lacked `embd_id`. `Dataset` in DevRAG still lacks `parser_id`, `parser_config`, etc., because DevRAG lacks the chunkers to support them.

## Data Flow Gaps

### Document Upload & Parsing Pipeline
- **RAGFlow Flow:** `Upload` -> `Task Created` -> `Worker fetches Dataset parser_id` -> `Selects deepdoc Parser (e.g. PDF)` -> `Selects rag/app Chunker (e.g. naive)` -> `Chunks` -> `Embedding` -> `Infinity`.
- **DevRAG Flow:** `Upload` -> `Task Created` -> `Worker hardcodes Txt/Md parser` -> `Worker hardcodes GeneralChunker` -> `Chunks` -> `Embedding` -> `Infinity`.
- **Priority:** **P1 (Core RAG Behavior).** DevRAG cannot process standard enterprise documents (PDFs, Office docs) and cannot execute strategy-specific chunking.

---

## Actionable Next Steps
The highest-priority unresolved behavioral gap is the **Document Parsing & Chunking Pipeline (P1)**. DevRAG cannot parse PDFs, Excel, Word, or PPT files, and relies on a hardcoded generic text chunker instead of RAGFlow's strategy-specific chunkers (naive, QA, resume, etc.).
