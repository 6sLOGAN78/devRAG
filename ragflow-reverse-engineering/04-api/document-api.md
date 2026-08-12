# Document Management API

## Level 1: Endpoint Specification Overview

The Document Management APIs allow users and SDKs to upload raw document files, trigger task parsing workers, inspect extraction status, query text chunks, and delete documents.

---

## Level 2: Comprehensive API Endpoints Specification

### 1. Document File Upload
- **Endpoint**: `POST /v1/document/upload`
- **Engine**: Python Quart (`api/apps/restful_apis/document_api.py`) & Go Gin (`internal/handler/document.go`)
- **Auth Level**: JWT / API Key (`login_required`)
- **Content-Type**: `multipart/form-data`
- **Form Fields**:
  - `file`: Raw document binary payload (PDF, DOCX, PPTX, XLSX, TXT).
  - `kb_id`: Target knowledge base ID string.

---

### 2. Run Parsing & Chunking Tasks
- **Endpoint**: `POST /v1/document/run`
- **Engine**: Python Quart (`api/apps/restful_apis/document_api.py`)
- **Auth Level**: JWT / API Key
- **Request Payload**:
  ```json
  {
    "doc_ids": ["doc-112233", "doc-445566"],
    "run": "1"
  }
  ```

---

### 3. Change Chunk Enable Status
- **Endpoint**: `POST /v1/document/change_status`
- **Engine**: Python Quart (`api/apps/restful_apis/document_api.py`)
- **Auth Level**: JWT / API Key
- **Request Payload**:
  ```json
  {
    "doc_id": "doc-112233",
    "status": "1"
  }
  ```

---

### 4. Remove Document
- **Endpoint**: `POST /v1/document/rm`
- **Engine**: Python Quart (`api/apps/restful_apis/document_api.py`)
- **Auth Level**: JWT / API Key
- **Request Payload**: `{ "doc_id": "doc-112233" }`

### Source File References

- Python Document API Blueprint: [`api/apps/restful_apis/document_api.py`](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/document_api.py)
- Go Document Handler: [`internal/handler/document.go`](file:///home/logan78/Desktop/ragflow/internal/handler/document.go)
- Document Service: [`api/db/services/document_service.py`](file:///home/logan78/Desktop/ragflow/api/db/services/document_service.py)
