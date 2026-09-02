## Objective
Implement Tenant context extraction and Python Auth Middleware to share session validation across dual stacks.

## Why Now?
RAGFlow is multi-tenant. Both Go and Python servers need to extract the `tenant_id` from the authenticated user to isolate data.

## Dependencies
- 03-authentication-flow
- 02-python-quart-service

## Implementation Tasks
- [ ] Go: Update Auth middleware to inject `tenant_id` into Gin context.
- [ ] Python: Implement a decorator/middleware in Quart to validate the JWT (or call Go/Redis to validate) and inject `tenant_id` into `g`.
- [ ] Create a `/api/v1/user/info` endpoint in Go to fetch current user profile.

## Components
- Tenant Context Middleware (Go/Python)

## Files
- `internal/middleware/auth.go` (update)
- `api/apps/auth_decorator.py`
- `internal/handler/user.go`

## Interfaces
- `GET /api/v1/user/info`

## Data Changes
N/A

## Data Flow
Client (JWT) -> Middleware -> Validates via Redis/Secret -> Context holds `tenant_id`

## Testing
- Test that Go and Python protected endpoints properly reject requests without tokens, and properly extract `tenant_id` with valid tokens.

## Deliverable
Multi-tenant security context active on both servers.

## Definition of Done
- Context (`c.Get("tenant_id")` or `g.tenant_id`) is available in protected handlers in both languages.

## Next Subphase
Phase 03 - 01-dataset-crud-api