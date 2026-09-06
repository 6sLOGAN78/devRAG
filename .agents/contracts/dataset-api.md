# Dataset API Contract

## Overview
Datasets (Knowledge Bases) are the core parent resource for documents. They are bound securely to the authenticated tenant and isolated from cross-tenant access.

## Endpoints

### `POST /api/v1/dataset`
Creates a dataset.
**Requires:** Authentication and valid tenant membership (non-`invite`).
**Payload:**
```json
{
  "name": "My Knowledge Base",
  "description": "Optional desc"
}
```
**Response:**
Returns the Dataset object securely mapping `tenant_id`, `created_by`, and `status`.

### `GET /api/v1/dataset/list`
Lists datasets owned by the currently resolved `tenant_id`.
**Requires:** Authentication and valid tenant membership.
**Response:**
```json
{
  "datasets": [
    {
      "id": "uuid",
      "name": "My Knowledge Base",
      "tenant_id": "current-tenant",
      ...
    }
  ]
}
```

### `DELETE /api/v1/dataset/:id`
Deletes a dataset permanently from the database.
**Requires:** Authentication and valid tenant membership.
**Behavior:**
- The request enforces `WHERE id = ? AND tenant_id = ?`.
- Cross-tenant requests will gracefully return `404 Not Found`.

## DB Isolation
- `Dataset` is bound strictly to `tenant_id`.
- Handlers extract `tenant_id` safely via `c.GetString("tenant_id")`.
- `created_by` maps accurately to `user_id`.
