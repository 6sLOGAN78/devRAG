# Agent & Canvas Workflow API

## Level 1: Endpoint Specification Overview

The Agent & Canvas Workflow APIs allow developers to create, update, export, inspect, and execute multi-node visual canvas workflow graphs programmatically.

---

## Level 2: Comprehensive API Endpoints Specification

### 1. Save Agent Canvas Graph (DSL)
- **Endpoint**: `POST /v1/canvas/set`
- **Engine**: Python Quart (`api/apps/restful_apis/agent_api.py`)
- **Auth Level**: JWT / API Key
- **Request Payload**:
  ```json
  {
    "id": "canvas-998877",
    "title": "Financial Audit Agent",
    "description": "Multi-stage graph analyzing annual reports",
    "dsl": {
      "nodes": [
        {"id": "begin", "label": "Begin"},
        {"id": "retrieval_1", "label": "Retrieval"},
        {"id": "llm_1", "label": "LLM"}
      ],
      "edges": [
        {"source": "begin", "target": "retrieval_1"},
        {"source": "retrieval_1", "target": "llm_1"}
      ]
    }
  }
  ```

---

### 2. Stream Agent Canvas Execution
- **Endpoint**: `POST /v1/canvas/completion`
- **Engine**: Python Quart (`api/apps/restful_apis/agent_api.py`)
- **Auth Level**: JWT / API Key
- **Request Payload**:
  ```json
  {
    "id": "canvas-998877",
    "message": "Audit Q3 balance sheet discrepancies",
    "stream": true
  }
  ```
- **SSE Stream Output**: Emits node execution state events (`node_start`, `node_output`, `token_stream`, `node_finish`).

---

### 3. Public Agent Bot Completion Endpoint
- **Endpoint**: `POST /api/v1/agentbots/:agent_id/completions`
- **Engine**: Go Gin (`cmd/ragflow_server.go:L215` & `internal/handler/bot.go`)
- **Auth Level**: Beta Token (`BetaAuthMiddleware`)

### Source File References

- Python Agent API Blueprint: [`api/apps/restful_apis/agent_api.py`](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/agent_api.py)
- Go Agent Handler: [`internal/handler/agent.go`](file:///home/logan78/Desktop/ragflow/internal/handler/agent.go)
- Canvas Service: [`api/db/services/canvas_service.py`](file:///home/logan78/Desktop/ragflow/api/db/services/canvas_service.py)
