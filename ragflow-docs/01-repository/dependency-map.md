# Module Dependency Map

## Level 1: System Dependency Graph

This document details the dependencies between architectural layers, third-party libraries, storage engines, and internal modules across the RAGFlow monorepo.

---

## Level 2: Inter-Module Dependency Architecture

```mermaid
graph TD
    subgraph Frontend_Layer ["Frontend SPA (web/src)"]
        UI_Pages["Pages & Components"]
        Zustand_Hooks["Zustand Stores (hooks/)"]
        API_Client["API Client / Axios Interceptor"]
        UI_Pages --> Zustand_Hooks --> API_Client
    end

    subgraph Go_Backend ["Go Engine (cmd/ & internal/)"]
        Gin_Router["Gin Router (internal/router)"]
        Auth_Handler["Auth Handler (internal/handler/auth.go)"]
        Services_Go["Service Layer (internal/service)"]
        DAO_Go["DAO Layer (internal/dao)"]
        Gin_Router --> Auth_Handler --> Services_Go --> DAO_Go
    end

    subgraph Python_Backend ["Python Engine (api/, agent/, deepdoc/, rag/)"]
        Quart_App["Quart App (api/apps)"]
        Auth_Py["Login Decorator (api/apps/__init__.py)"]
        Agent_Canvas["Agent Engine (agent/component)"]
        RAG_Search["RAG Hybrid Search (rag/retrieval)"]
        DeepDoc_Vision["DeepDoc Layout/TSR/OCR (deepdoc/vision)"]
        Quart_App --> Auth_Py --> Agent_Canvas & RAG_Search & DeepDoc_Vision
    end

    subgraph Data_Infrastructure ["Data Infrastructure"]
        MySQL[("MySQL / OceanBase DB")]
        Redis[("Redis Cache & Lock")]
        MinIO[("MinIO Object Storage")]
        VectorStores[("Vector Stores (Infinity/ES/Qdrant)")]
    end

    API_Client -->|HTTP / REST / SSE| Gin_Router
    API_Client -->|HTTP / REST / SSE| Quart_App

    DAO_Go --> MySQL
    DAO_Go --> Redis

    Auth_Py --> MySQL
    Agent_Canvas --> VectorStores
    DeepDoc_Vision --> MinIO
    RAG_Search --> VectorStores
```

---

## Module Dependency Matrix

| Requiring Module | Dependent Module | Communication Protocol / Mechanism | Source File References |
| :--- | :--- | :--- | :--- |
| `web/src` | `cmd/ragflow_server.go` | HTTP REST / Bearer Token Auth | [`web/src/routes.tsx`](file:///home/logan78/Desktop/ragflow/web/src/routes.tsx#L28) |
| `web/src` | `api/ragflow_server.py` | HTTP SSE (Server-Sent Events) | [`web/src/pages/agent/canvas/index.tsx`](file:///home/logan78/Desktop/ragflow/web/src/pages/agent/canvas/index.tsx) |
| `internal/handler` | `internal/service` | In-process Go interface calls | [`internal/router/router.go`](file:///home/logan78/Desktop/ragflow/internal/router/router.go#L65) |
| `internal/service` | `internal/dao` | GORM SQL queries | [`internal/dao/user.go`](file:///home/logan78/Desktop/ragflow/internal/dao/user.go) |
| `api/apps/restful_apis` | `api/db/services` | Peewee ORM context calls | [`api/apps/__init__.py`](file:///home/logan78/Desktop/ragflow/api/apps/__init__.py#L128) |
| `agent/component` | `common/doc_store` | Python class instantiation | [`agent/component/retrieval.py`](file:///home/logan78/Desktop/ragflow/agent/component/retrieval.py) |
| `deepdoc/parser` | `deepdoc/vision` | PyTorch inference model execution | [`deepdoc/vision/layout_recognizer.py`](file:///home/logan78/Desktop/ragflow/deepdoc/vision/layout_recognizer.py) |
