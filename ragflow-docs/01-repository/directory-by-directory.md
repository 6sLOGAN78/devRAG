# Directory-by-Directory Breakdown

## Level 1: Purpose & Overview

This document presents an exhaustive breakdown of every major top-level directory in the RAGFlow repository (`/home/logan78/Desktop/ragflow`), providing language specifications, architectural roles, and internal module organization.

---

## Level 2: Detailed Folder Analysis

### 1. `admin/`
- **Role**: Python-based administration client and server services.
- **Contents**:
  - `admin/client/`: Python CLI client and HTTP utilities.
  - `admin/server/`: Python backend admin routes and services.

### 2. `agent/`
- **Role**: Python agent workflow canvas execution framework.
- **Contents**:
  - `agent/component/`: Visual canvas node implementations ([`agent/component/`](file:///home/logan78/Desktop/ragflow/agent/component)):
    - `llm.py`: Large Language Model node handler.
    - `switch.py` & `categorize.py`: Conditional branching logic.
  - `agent/plugin/`: Global plugin manager ([`agent/plugin/__init__.py`](file:///home/logan78/Desktop/ragflow/agent/plugin)).
  - `agent/tools/`: Integration tools (Wikipedia, Google Search, Tavily, ArXiv, DuckDuckGo).

### 3. `api/`
- **Role**: Python ASGI web application built with Quart.
- **Contents**:
  - `api/ragflow_server.py`: Python server entry point ([`api/ragflow_server.py`](file:///home/logan78/Desktop/ragflow/api/ragflow_server.py#L90)).
  - `api/apps/`: Quart application initialization, CORS, authentication decorators ([`api/apps/__init__.py`](file:///home/logan78/Desktop/ragflow/api/apps/__init__.py#L61)).
  - `api/apps/restful_apis/`: REST API route modules (`kb_app.py`, `document_api.py`, `user_api.py`, `agent_api.py`, `chat_api.py`, `mcp_api.py`, `openai_api.py`).
  - `api/db/`: Peewee database tables ([`api/db/db_models.py`](file:///home/logan78/Desktop/ragflow/api/db/db_models.py)) and data service classes (`user_service.py`, `document_service.py`, etc.).

### 4. `cmd/`
- **Role**: Executable entry points for Go binaries.
- **Contents**:
  - `cmd/ragflow_server.go`: Main Go API server entry point supporting `--admin`, `--api`, `--ingestor`, and `--syncer` modes ([`cmd/ragflow_server.go`](file:///home/logan78/Desktop/ragflow/cmd/ragflow_server.go#L81)).
  - `cmd/ragflow-cli.go`: Interactive terminal CLI entry point ([`cmd/ragflow-cli.go`](file:///home/logan78/Desktop/ragflow/cmd/ragflow-cli.go)).

### 5. `common/`
- **Role**: Shared Python libraries, settings, and vector store connectors.
- **Contents**:
  - `common/doc_store/`: Vector DB adapters for Infinity, Elasticsearch, OpenSearch, OceanBase, Qdrant, Milvus, PGVector ([`common/doc_store/`](file:///home/logan78/Desktop/ragflow/common/doc_store)).
  - `common/settings.py`: Global environment settings loader.
  - `common/log_utils.py`: Central logger initialization.

### 6. `deepdoc/`
- **Role**: Deep Document Parsing & Computer Vision suite.
- **Contents**:
  - `deepdoc/vision/`: YOLOv8 layout recognizer ([`deepdoc/vision/layout_recognizer.py`](file:///home/logan78/Desktop/ragflow/deepdoc/vision/layout_recognizer.py)), TSR table structure recognizer ([`deepdoc/vision/table_structure_recognizer.py`](file:///home/logan78/Desktop/ragflow/deepdoc/vision/table_structure_recognizer.py)), and OCR engine ([`deepdoc/vision/ocr.py`](file:///home/logan78/Desktop/ragflow/deepdoc/vision/ocr.py)).
  - `deepdoc/parser/`: Document type parsers (PDF, DOCX, PPTX, Excel, HTML, Image, Audio).

### 7. `internal/`
- **Role**: Go backend internal architecture.
- **Contents**:
  - `internal/router/`: Gin HTTP router configuration ([`internal/router/router.go`](file:///home/logan78/Desktop/ragflow/internal/router/router.go#L141)).
  - `internal/handler/`: Gin request handlers (`auth.go`, `user.go`, `document.go`, `chat.go`, `agent.go`, `mcp.go`).
  - `internal/service/`: Business logic implementations.
  - `internal/dao/`: Data access objects interfacing with GORM/MySQL.
  - `internal/syncer/`: Background synchronization tasks.

### 8. `rag/`
- **Role**: RAG retrieval algorithms, tokenization, and LLM configuration.
- **Contents**:
  - `rag/nlp/`: Language-specific tokenization and search implementations (e.g., `search.py`).
  - `rag/llm/`: Model wrapper logic for OpenAI, local deployments, embedding, and cross-encoder re-rankers.

### 9. `web/`
- **Role**: Single-Page React Web Application.
- **Contents**:
  - `web/src/routes.tsx`: React Router 7 page definitions ([`web/src/routes.tsx`](file:///home/logan78/Desktop/ragflow/web/src/routes.tsx#L28)).
  - `web/src/pages/`: User interface pages (`login-next`, `datasets`, `agent`, `next-chats`, `user-setting`, `admin`).
  - `web/src/components/`: Reusable React components (chunking dialogs, parse config, LLM selectors, markdown renderer).
