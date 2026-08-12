# User & Tenant Management API

## Level 1: Endpoint Specification Overview

The User & Tenant Management APIs allow authenticated users to retrieve profile data, switch active tenants, update user preferences, change passwords, and configure organization settings.

---

## Level 2: Comprehensive API Endpoints Specification

### 1. Get Tenant Info
- **Endpoint**: `GET /v1/user/tenant_info`
- **Engine**: Go Gin (`internal/handler/tenant.go`)
- **Auth Level**: JWT / Session Cookie
- **Response Payload**:
  ```json
  {
    "retcode": 0,
    "retmsg": "success",
    "data": {
      "tenant_id": "t-98765",
      "name": "Acme Corp Workspace",
      "role": "owner",
      "llm_id": "deepseek-chat"
    }
  }
  ```

---

### 2. Tenant List
- **Endpoint**: `GET /v1/tenant/list`
- **Engine**: Go Gin (`internal/handler/tenant.go`)
- **Auth Level**: JWT / Session Cookie
- **Response Payload**: Array of accessible workspaces and roles for the authenticated user.

---

### 3. Update User Settings
- **Endpoint**: `POST /v1/user/setting`
- **Engine**: Go Gin (`internal/handler/user.go`) & Python (`api/apps/restful_apis/user_api.py`)
- **Auth Level**: JWT / Session Cookie
- **Request Payload**:
  ```json
  {
    "nickname": "Jane Admin",
    "avatar": "https://example.com/avatar.png",
    "language": "English"
  }
  ```

---

### 4. Change Password
- **Endpoint**: `POST /v1/user/setting/password`
- **Engine**: Go Gin (`internal/handler/user.go`)
- **Auth Level**: JWT / Session Cookie
- **Request Payload**:
  ```json
  {
    "old_password": "CurrentPassword123!",
    "new_password": "NewSecretPassword456!"
  }
  ```

### Source File References

- Go User Handler: [`internal/handler/user.go`](file:///home/logan78/Desktop/ragflow/internal/handler/user.go)
- Go Tenant Handler: [`internal/handler/tenant.go`](file:///home/logan78/Desktop/ragflow/internal/handler/tenant.go)
- Python User API: [`api/apps/restful_apis/user_api.py`](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/user_api.py)
- User Database Model: [`api/db/db_models.py`](file:///home/logan78/Desktop/ragflow/api/db/db_models.py)
