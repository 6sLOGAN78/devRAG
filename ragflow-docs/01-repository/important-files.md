# Important Files Catalog

## Level 1: Key Files & Impact Ratings

This document catalogues the most critical files across the RAGFlow codebase, categorized by architectural layer and annotated with impact ratings (5-star scale) and line references.

---

## Level 2: Critical Code Reference Catalog

### 1. Backend Server Entry Points & Gateways

| File Path | Stack | Impact | Description & Critical Lines |
| :--- | :--- | :--- | :--- |
| [`cmd/ragflow_server.go`](file:///home/logan78/Desktop/ragflow/cmd/ragflow_server.go#L81) | Go | ⭐⭐⭐⭐⭐ | Entry point for Go engine. Parses CLI flags (`--admin`, `--api`, `--ingestor`, `--syncer`), initializes Gin server, sets up DB migration, and starts HTTP server on port 9380. |
| [`api/ragflow_server.py`](file:///home/logan78/Desktop/ragflow/api/ragflow_server.py#L90) | Python | ⭐⭐⭐⭐⭐ | Entry point for Python ASGI server. Initializes logger, Peewee DB tables, runtime config, background progress updater thread, and starts Quart ASGI app. |
| [`api/apps/__init__.py`](file:///home/logan78/Desktop/ragflow/api/apps/__init__.py#L61) | Python | ⭐⭐⭐⭐⭐ | Core Quart app initialization (`app = Quart(__name__)`), CORS configuration, OpenAPI QuartSchema, and `login_required` authentication decorator supporting JWT, API Tokens, and Session cookies. |
| [`internal/router/router.go`](file:///home/logan78/Desktop/ragflow/internal/router/router.go#L141) | Go | ⭐⭐⭐⭐⭐ | Central Gin router setup. Defines unauthenticated routes (`/system/config`, `/auth/login`), beta-token auth routes (`/searchbots`), and authenticated route groups (`/v1/user/info`, `/api/v1`). |

### 2. Authentication & Data Persistence Models

| File Path | Stack | Impact | Description & Critical Lines |
| :--- | :--- | :--- | :--- |
| [`api/db/db_models.py`](file:///home/logan78/Desktop/ragflow/api/db/db_models.py) | Python | ⭐⭐⭐⭐⭐ | Peewee database model definitions: `User`, `Tenant`, `UserTenant`, `APIToken`, `Knowledgebase`, `Document`, `Task`, `Dialog`, `Canvas`. |
| [`api/db/services/user_service.py`](file:///home/logan78/Desktop/ragflow/api/db/services/user_service.py#L33) | Python | ⭐⭐⭐⭐⭐ | User authentication, PBKDF2/Bcrypt password hashing, token validation (`query()` access token checks), and tenant relationship lookup. |
| [`internal/handler/auth.go`](file:///home/logan78/Desktop/ragflow/internal/handler/auth.go) | Go | ⭐⭐⭐⭐⭐ | Go authentication middleware (`AuthMiddleware()`, `BetaAuthMiddleware()`), extracting Bearer tokens and validating sessions. |
| [`internal/dao/user.go`](file:///home/logan78/Desktop/ragflow/internal/dao/user.go) | Go | ⭐⭐⭐⭐ | Go Data Access Object for querying User records from GORM/MySQL. |

### 3. Deep Document Parsing & AI Engine

| File Path | Stack | Impact | Description & Critical Lines |
| :--- | :--- | :--- | :--- |
| [`deepdoc/vision/layout_recognizer.py`](file:///home/logan78/Desktop/ragflow/deepdoc/vision/layout_recognizer.py) | Python | ⭐⭐⭐⭐⭐ | YOLOv8-based computer vision layout analysis for identifying headers, text blocks, visual tables, and figures in PDF page images. |
| [`deepdoc/vision/table_structure_recognizer.py`](file:///home/logan78/Desktop/ragflow/deepdoc/vision/table_structure_recognizer.py) | Python | ⭐⭐⭐⭐⭐ | Table Structure Recognition (TSR) model for converting visual bounding box table representations into HTML text matrices. |
| [`agent/component/llm.py`](file:///home/logan78/Desktop/ragflow/agent/component/llm.py) | Python | ⭐⭐⭐⭐⭐ | Canvas LLM component node handler that executes multi-turn conversations and handles streaming token output. |
| [`rag/utils/`](file:///home/logan78/Desktop/ragflow/rag/utils) | Python | ⭐⭐⭐⭐⭐ | Multi-vector store adapter interface binding Infinity, Elasticsearch, OceanBase, Qdrant, and Milvus. |

### 4. Frontend Single-Page Application

| File Path | Stack | Impact | Description & Critical Lines |
| :--- | :--- | :--- | :--- |
| [`web/src/routes.tsx`](file:///home/logan78/Desktop/ragflow/web/src/routes.tsx#L28) | TS/React | ⭐⭐⭐⭐⭐ | React Router 7 setup with `withLazyRoute` lazy loading, auth redirects, layout bindings, and public share routes. |
| [`web/src/app.tsx`](file:///home/logan78/Desktop/ragflow/web/src/app.tsx#L1) | TS/React | ⭐⭐⭐⭐⭐ | Root React application element initializing i18n, global state providers, and theme wrappers. |
| [`web/src/pages/agent/canvas/index.tsx`](file:///home/logan78/Desktop/ragflow/web/src/pages/agent/canvas/index.tsx) | TS/React | ⭐⭐⭐⭐⭐ | Visual agent canvas node flow builder based on `@xyflow/react`. |
