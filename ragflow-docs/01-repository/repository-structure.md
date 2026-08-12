# Repository Structure

## Level 1: Monorepo Topology & Design Principles

RAGFlow is organized as a unified multi-language monorepo housing frontend TypeScript/React application, dual-stack Go and Python API backend servers, deep document processing engines, agent graph runtimes, CLI utilities, and infrastructure configuration files.

### Architectural Principles

1. **Separation of Gateway vs Compute**: High-concurrency routing, auth checks, system administration, and ingestion queuing are hosted in Go (`cmd/` & `internal/`), while heavy ML/AI pipelines, embedding calculations, and agent graph canvas evaluations run in Python (`api/`, `agent/`, `deepdoc/`, `rag/`).
2. **Modular Ingestion Pipeline**: DeepDoc document parsing operates as a standalone package (`deepdoc/`) that can be executed independently or invoked via background worker threads.
3. **Decoupled DocStore Interface**: Storage layer (`common/doc_store/`) abstracts vector databases so RAGFlow can operate seamlessly over Infinity, Elasticsearch, OpenSearch, OceanBase, Qdrant, Milvus, or PGVector.
4. **Single-Page Application Frontend**: Frontend UI (`web/`) communicates exclusively via REST APIs and Server-Sent Events (SSE) with the backend engine.

---

## Level 2: Comprehensive Directory Tree

```
/home/logan78/Desktop/ragflow/
├── admin/                      # Python-based administration client and server services
│   ├── client/                 # Python CLI client and HTTP utilities
│   └── server/                 # Python backend admin routes and services
├── agent/                      # Python Agent Execution Engine & Component Nodes
│   ├── component/              # Visual canvas component nodes (LLM, Switch, Categorize, etc.)
│   ├── plugin/                 # Plugin extension manager
│   └── tools/                  # Agent tool definitions (Tavily, Google, Wikipedia, Wolfram, etc.)
├── api/                        # Python Quart ASGI Web Backend
│   ├── apps/                   # Quart routes & REST API definitions
│   │   └── restful_apis/       # Endpoints (dataset, document, chat, agent, user, etc.)
│   ├── db/                     # Peewee ORM database models, services, & migrations
│   │   ├── db_models.py        # Central database tables (User, Tenant, Knowledgebase, Document, etc.)
│   │   └── services/           # Service layer classes (UserService, DocumentService, etc.)
│   └── ragflow_server.py       # Python ASGI server entry point
├── bin/                        # Shell scripts and compiled binary utilities
├── cmd/                        # Go Executable Entry Points
│   ├── ragflow_server.go       # Go API & Ingestion server entry point
│   └── ragflow-cli.go          # Go CLI interactive terminal entry point
├── common/                     # Shared Python utilities, DB config, settings, doc_store adapters
├── conf/                       # System configuration files (service_conf.yaml, model maps)
├── deepdoc/                    # Deep Document Parsing Engine (Layout, TSR, OCR, Parser)
├── docker/                     # Dockerfiles, Docker Compose profiles, Nginx configs
├── internal/                   # Go Backend Internal Package Architecture
│   ├── admin/                  # Go admin handlers & handlers_ee
│   ├── agent/                  # Go agent bridge, canvas, audio, tool execution
│   ├── dao/                    # Data Access Objects (User, Tenant, Dataset, Document, etc.)
│   ├── handler/                # Gin HTTP Handlers (Auth, User, Tenant, Document, Chat, Agent, etc.)
│   ├── ingestion/              # Ingestion service & document processing pipeline
│   ├── router/                 # Gin HTTP Route definitions (router.go, agent_routes.go)
│   ├── service/                # Go Service layer business logic
│   └── syncer/                 # Task synchronization & state syncer
├── rag/                        # RAG Engine (Hybrid retrieval, NLP tokenization, Re-ranking)
└── web/                        # React TypeScript Web Single Page Application
    ├── src/                    # Web application source files
    │   ├── components/         # Reusable React UI components
    │   ├── hooks/              # Zustand custom React hooks & stores
    │   ├── pages/              # SPA Pages (datasets, agent, chat, search, user-setting, admin)
    │   └── routes.tsx          # React Router v7 routes & lazy load definitions
```

---

## Key Module Links

- Go Backend Gateway: [`cmd/ragflow_server.go`](file:///home/logan78/Desktop/ragflow/cmd/ragflow_server.go#L81)
- Go Routers: [`internal/router/router.go`](file:///home/logan78/Desktop/ragflow/internal/router/router.go#L141)
- Python Server: [`api/ragflow_server.py`](file:///home/logan78/Desktop/ragflow/api/ragflow_server.py#L90)
- Python REST APIs: [`api/apps/restful_apis/`](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis)
- Database Models: [`api/db/db_models.py`](file:///home/logan78/Desktop/ragflow/api/db/db_models.py)
- Web App Routes: [`web/src/routes.tsx`](file:///home/logan78/Desktop/ragflow/web/src/routes.tsx#L28)
- DeepDoc Layout Recognizer: [`deepdoc/vision/layout_recognizer.py`](file:///home/logan78/Desktop/ragflow/deepdoc/vision/layout_recognizer.py)
