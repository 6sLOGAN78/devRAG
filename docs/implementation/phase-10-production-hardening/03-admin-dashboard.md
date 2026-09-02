## Objective
Build the Admin management UI and APIs for tenant, user, and system resource management.

## Why Now?
System administrators need visibility into tenant usage and user accounts.

## Dependencies
- Phase 03

## Implementation Tasks
- [ ] Go API: Implement `admin` protected endpoints (`/api/v1/admin/users`).
- [ ] Frontend: Build `pages/admin/` routes (User Management, Tenant Quotas).
- [ ] Implement Role-Based Access Control (RBAC) middleware verifying `role == 'admin'`.

## Components
- Admin APIs
- Admin UI
- RBAC Middleware

## Files
- `internal/handler/admin.go`
- `internal/middleware/rbac.go`
- `web/src/pages/admin/index.tsx`

## Interfaces
- Admin REST API

## Data Changes
N/A

## Data Flow
N/A

## Testing
- Verify standard users receive 403 Forbidden on Admin APIs.

## Deliverable
Enterprise administration capabilities.

## Definition of Done
- Admins can manage users and view system-wide stats.

## Next Subphase
04-deployment-manifests