# Master API Endpoint Catalog

## Level 1: Endpoint Catalog Overview

This document presents the complete API Endpoint Catalog for RAGFlow, listing endpoints across both the **Go Gin Engine** and the **Python Quart ASGI Engine**, annotated with HTTP methods, route paths, underlying controllers/handlers, required parameters, authentication levels, and functional descriptions.

---

## Level 2: Comprehensive API Endpoint Table

### 1. System & Authentication APIs

| HTTP Method | Route Path | Engine | Controller / Handler | Auth Level | Parameters & Request Body | Description |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `GET` | `/health` | Go | `systemHandler.Health` | None | None | System health status check. |
| `GET` | `/api/v1/system/ping` | Go | `systemHandler.Ping` | None | None | Basic server ping test. |
| `GET` | `/api/v1/system/config` | Go | `systemHandler.GetConfig` | None | None | Returns public system configurations. |
| `GET` | `/api/v1/system/version` | Go | `systemHandler.GetVersion` | None | None | Returns RAGFlow version string. |
| `GET` | `/api/v1/language` | Go | `systemHandler.Language` | None | None | Runtime language detection (`go` vs `python`). |
| `POST` | `/api/v1/auth/login` | Go | `userHandler.LoginByEmail` | None | JSON: `email`, `password` | Authenticate user by email & password. |
| `POST` | `/api/v1/users` | Go | `userHandler.Register` | None | JSON: `email`, `password`, `nickname` | Register a new user account. |
| `POST` | `/api/v1/auth/password/forgot/otp` | Go | `userHandler.ForgotSendOTP` | None | JSON: `email` | Send OTP for password reset. |
| `POST` | `/api/v1/auth/password/reset` | Go | `userHandler.ForgotResetPassword` | None | JSON: `email`, `otp`, `new_password` | Reset forgotten password. |
| `GET` | `/v1/user/info` | Go | `userHandler.Info` | JWT / Session | Header: `Authorization` | Retrieve current user profile & role. |
| `GET` | `/v1/user/tenant_info` | Go | `tenantHandler.TenantInfo` | JWT / Session | Header: `Authorization` | Retrieve tenant workspace details. |
| `GET` | `/v1/tenant/list` | Go | `tenantHandler.TenantList` | JWT / Session | Header: `Authorization` | List accessible tenant workspaces. |
| `POST` | `/v1/user/setting` | Go | `userHandler.Setting` | JWT / Session | JSON: `nickname`, `avatar`, `language` | Update user settings. |
| `POST` | `/v1/user/setting/password` | Go | `userHandler.ChangePassword` | JWT / Session | JSON: `old_password`, `new_password` | Change user password. |

---

### 2. Knowledge Base (Dataset) & Document APIs

| HTTP Method | Route Path | Engine | Controller / Handler | Auth Level | Parameters & Request Body | Description |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `POST` | `/v1/kb/create` | Python | `dataset_api.create` | JWT / API Key | JSON: `name`, `parser_id`, `embd_id` | Create a new knowledge base dataset. |
| `POST` | `/v1/kb/update` | Python | `dataset_api.update` | JWT / API Key | JSON: `kb_id`, `name`, `parser_id` | Update dataset configurations. |
| `POST` | `/v1/kb/rm` | Python | `dataset_api.rm` | JWT / API Key | JSON: `kb_id` | Delete a dataset and its document index. |
| `GET` | `/v1/kb/list` | Python | `dataset_api.list_kbs` | JWT / API Key | Query: `page`, `page_size`, `keywords` | List knowledge bases for the current tenant. |
| `POST` | `/v1/document/upload` | Python / Go | `document_api.upload` | JWT / API Key | Multipart: `file`, `kb_id` | Upload a document file to a dataset. |
| `POST` | `/v1/document/run` | Python | `document_api.run` | JWT / API Key | JSON: `doc_ids`, `run` | Trigger parsing & chunking execution tasks. |
| `POST` | `/v1/document/change_status` | Python | `document_api.change_status` | JWT / API Key | JSON: `doc_id`, `status` | Enable or disable document chunks in search. |
| `POST` | `/v1/document/rm` | Python | `document_api.rm` | JWT / API Key | JSON: `doc_id` | Delete document and remove vector chunks. |
| `GET` | `/v1/document/list` | Python | `document_api.list_docs` | JWT / API Key | Query: `kb_id`, `page`, `keywords` | List documents inside a dataset. |
| `GET` | `/v1/chunk/list` | Python | `chunk_api.list_chunks` | JWT / API Key | Query: `doc_id`, `page`, `keywords` | Retrieve chunk text list and status. |
| `POST` | `/v1/chunk/create` | Python | `chunk_api.create` | JWT / API Key | JSON: `doc_id`, `content_with_weight` | Create a manual chunk. |

---

### 3. Agent & Canvas Workflow APIs

| HTTP Method | Route Path | Engine | Controller / Handler | Auth Level | Parameters & Request Body | Description |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `POST` | `/v1/canvas/set` | Python | `agent_api.set_canvas` | JWT / API Key | JSON: `id`, `title`, `dsl` | Create or update agent canvas flow graph. |
| `GET` | `/v1/canvas/get/:id` | Python | `agent_api.get_canvas` | JWT / API Key | Path: `id` | Get agent canvas DSL topology. |
| `POST` | `/v1/canvas/completion` | Python | `agent_api.completion` | JWT / API Key | JSON: `id`, `message`, `stream` | Execute agent graph flow with streaming. |
| `GET` | `/v1/canvas/list` | Python | `agent_api.list_canvas` | JWT / API Key | Query: `page`, `keywords` | List user agents. |
| `POST` | `/v1/canvas/rm` | Python | `agent_api.rm_canvas` | JWT / API Key | JSON: `id` | Delete an agent canvas workflow. |

---

### 4. Chat & Dialogue Playground APIs

| HTTP Method | Route Path | Engine | Controller / Handler | Auth Level | Parameters & Request Body | Description |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `POST` | `/v1/api/dialog/set` | Python | `chat_api.set_dialog` | JWT / API Key | JSON: `name`, `kb_ids`, `llm_id` | Create or update a dialogue configuration. |
| `GET` | `/v1/api/dialog/list` | Python | `chat_api.list_dialogs` | JWT / API Key | Query: `page`, `keywords` | List active dialogue assistants. |
| `POST` | `/v1/api/dialog/rm` | Python | `chat_api.rm_dialog` | JWT / API Key | JSON: `dialog_id` | Remove a dialogue assistant. |
| `POST` | `/v1/api/chat/completion` | Python | `chat_api.completion` | JWT / API Key | JSON: `session_id`, `message`, `stream` | Stream RAG chat completion tokens (SSE). |
| `GET` | `/v1/api/session/list` | Python | `chat_api.list_sessions` | JWT / API Key | Query: `dialog_id` | List sessions under a dialogue assistant. |

---

### 5. Search Bots & MCP Server APIs

| HTTP Method | Route Path | Engine | Controller / Handler | Auth Level | Parameters & Request Body | Description |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/searchbots/ask` | Go | `searchBotHandler.Ask` | Beta Auth | JSON: `question`, `kb_ids` | High-performance search bot query. |
| `POST` | `/api/v1/searchbots/retrieval_test`| Go | `searchBotHandler.RetrievalTest`| Beta Auth | JSON: `question`, `kb_ids` | Retrieval accuracy testing endpoint. |
| `POST` | `/api/v1/mcp` | Go | `mcpServerHandler.HandleMCP` | Beta Auth | JSON: MCP JSON-RPC protocol body | Model Context Protocol server endpoint. |

### Core Source References

- Go Router Setup: [`internal/router/router.go`](file:///home/logan78/Desktop/ragflow/internal/router/router.go#L141)
- Python Restful APIs Directory: [`api/apps/restful_apis/`](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis)
- Python App Registration: [`api/apps/__init__.py`](file:///home/logan78/Desktop/ragflow/api/apps/__init__.py#L61)
