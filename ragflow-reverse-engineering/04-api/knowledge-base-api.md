# Knowledge Base (Dataset) API

## Level 1: Endpoint Specification Overview

The Knowledge Base (Dataset) APIs enable users and SDK applications to programmatically create, query, configure, and delete knowledge bases.

---

## Level 2: Comprehensive API Endpoints Specification

### 1. Create Knowledge Base
- **Endpoint**: `POST /v1/kb/create`
- **Engine**: Python Quart (`api/apps/restful_apis/dataset_api.py`)
- **Auth Level**: JWT / API Key (`login_required`)
- **Request Payload**:
  ```json
  {
    "name": "Financial Reports 2026",
    "parser_id": "naive",
    "embd_id": "BAAI/bge-large-en-v1.5",
    "language": "English",
    "description": "Annual financial statements and audit reports"
  }
  ```
- **Response Payload**:
  ```json
  {
    "retcode": 0,
    "retmsg": "success",
    "data": {
      "kb_id": "kb-10020304"
    }
  }
  ```

---

### 2. List Knowledge Bases
- **Endpoint**: `GET /v1/kb/list`
- **Engine**: Python Quart / Go Gin
- **Auth Level**: JWT / API Key
- **Query Parameters**: `page` (default 1), `page_size` (default 30), `keywords` (string search)

---

### 3. Update Knowledge Base Configuration
- **Endpoint**: `POST /v1/kb/update`
- **Engine**: Python Quart (`api/apps/restful_apis/dataset_api.py`)
- **Auth Level**: JWT / API Key
- **Request Payload**:
  ```json
  {
    "kb_id": "kb-10020304",
    "parser_id": "paper",
    "pagerank": 0,
    "parser_config": {
      "chunk_token_num": 256,
      "layout_recognize": true
    }
  }
  ```

---

### 4. Remove Knowledge Base
- **Endpoint**: `POST /v1/kb/rm`
- **Engine**: Python Quart (`api/apps/restful_apis/dataset_api.py`)
- **Auth Level**: JWT / API Key
- **Request Payload**: `{ "kb_id": "kb-10020304" }`

### Source File References

- Python Dataset API Blueprint: [`api/apps/restful_apis/dataset_api.py`](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/dataset_api.py)
- Go Dataset Handler: [`internal/handler/datasets.go`](file:///home/logan78/Desktop/ragflow/internal/handler/datasets.go)
- Knowledgebase Service: [`api/db/services/knowledgebase_service.py`](file:///home/logan78/Desktop/ragflow/api/db/services/knowledgebase_service.py)
