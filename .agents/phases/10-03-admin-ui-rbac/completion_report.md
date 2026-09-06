# Phase 10-03 Completion Report: Admin Management UI, APIs & RBAC

## A. Existing Architecture

The system uses a tenant-scoped multi-tenancy model. 
```text
User (Global identity)
      ↓
UserTenant (Links user to tenant)
      ↓
Role (owner, admin, normal, invite)
```
There is **no global admin** concept in the system schema, as `User` has no role column. All administrative APIs developed in this phase evaluate administrative capability within the context of a given Tenant (`X-Tenant-ID` or default assigned tenant).

```text
Authentication (Validates token)
      ↓
Principal (user_id, tenant_id, role)
      ↓
RBAC (RequireAdmin)
      ↓
Admin APIs (Users, Quotas/Stats)
```

## B. RBAC

- **Role Representation:** The roles are enum strings: `"owner"`, `"admin"`, `"normal"`, `"invite"`.
- **Admin Detection:** Allowed roles are `"admin"` and `"owner"`.
- **Middleware (`internal/middleware/rbac.go`):** Executes after the Auth middleware. Uses `c.GetString("role")`. 
- **Ordering:** `Recovery` -> `RequestID` -> `StructuredLogger` -> `Auth` -> `RequireAdmin` -> `Admin Handlers`
- **401 Behavior:** Returns 401 if missing authentication headers, invalid JWT, or inactive session.
- **403 Behavior:** Returns 403 `FORBIDDEN` if a valid session exists but the role is `"normal"` or `"invite"`.

## C. Admin API

All endpoints belong to the protected route group `/api/v1/admin/*`.

| Method | Endpoint                        | Purpose                          | Authorization       |
| ------ | ------------------------------- | -------------------------------- | ------------------- |
| GET    | `/api/v1/admin/stats`           | Fetch system stats for tenant    | Tenant owner/admin  |
| GET    | `/api/v1/admin/users`           | List users within tenant         | Tenant owner/admin  |
| PATCH  | `/api/v1/admin/users/:id/role`  | Change a user's role             | Tenant owner/admin  |
| DELETE | `/api/v1/admin/users/:id`       | Remove user from tenant          | Tenant owner/admin  |

## D. User Management

- **List:** Implemented. Returns all users assigned to the tenant via `user_tenant` join.
- **Mutations:** Admins can change a user's role or remove them from the tenant.
- **Self-Protection:** An admin cannot remove themselves or downgrade their own role unless another admin exists. 
- **Last-Admin Invariant:** Prevents deleting or demoting an admin if they are the last admin in the tenant.

## E. Tenant Management

There is no Global Admin. A user is only an admin of a specific tenant.
The system does not have dedicated Resource Quotas stored in the database yet, only rate limits.
System-wide metrics and user-management are inherently isolated to the current tenant. The Admin APIs enforce `tenant_id` context checking via `internal/service/admin.go`.

## F. System Statistics

- `TotalUsers`: Total rows in `user_tenant` matching `tenant_id`.
- `TotalDocuments`: Total rows in `document` matching `tenant_id`.
- `TotalDatasets`: Total rows in `dataset` matching `tenant_id`.
- `TotalChats`: Total rows in `chat_session` matching `tenant_id`.

## G. Frontend

- **Routes:** Added `/admin` and `/admin/users`.
- **Guards:** Added `AdminGuard` component to prevent non-admins from loading the dashboard routes.
- **Components:** Added `AdminOverview` and `AdminUsers`.
- **API Hooks:** Integrated smoothly with existing `apiClient`. Fixed a flaw in `hydrate` (useAuthStore) which lacked role propagation.
- **States:** Added Loading and Error states. Added confirmation dialogues for mutations.
- **Navigation:** Extended `MainLayout` to conditionally render the "Administration" sidebar item based on role.

## H. Security

- **Standard User → 403:** Proved via unit test and E2E scripts. `GET /api/v1/admin/stats` fails with `FORBIDDEN`.
- **Unauthenticated → 401:** Handled by standard Auth middleware and tested.
- **Forged Role:** Frontend role is only for UX routing. Modifying frontend React state won't allow API mutations. Backend extracts role strictly from `UserTenant` DB lookup on each request.
- **Direct API Access:** Directly CURLing will result in a 403.
- **Tenant Isolation:** Explicitly enforced since `tenant_id` is derived from the JWT Claims and verified against DB joins.
- **Admin Self-Protection:** Implemented in `UpdateUserRole` and `RemoveUserFromTenant`.

## I. Files Modified/Created

- `internal/middleware/rbac.go` (new)
- `internal/service/admin.go` (new)
- `internal/handler/admin.go` (new)
- `internal/router/router.go`
- `internal/handler/user.go`
- `internal/service/user.go`
- `web/src/routes.tsx`
- `web/src/layouts/main-layout.tsx`
- `web/src/components/AdminGuard.tsx` (new)
- `web/src/pages/admin/layout.tsx` (new)
- `web/src/pages/admin/index.tsx` (new)
- `web/src/pages/admin/users.tsx` (new)
- `tests/integration/admin_test.go` (new)
- `tests/e2e/playwright/tests/admin.spec.ts` (new)

## J. Tests

- **Unit/Integration:** Added `tests/integration/admin_test.go` verifying the entire matrix of roles (`admin`, `owner`, `normal`, `invite`, missing) against HTTP 403, 401, etc.
- **E2E/Security:** Added `admin.spec.ts` mimicking frontend UI block and direct API calls.
- **CI:** Maintained compatibility with `10-01` phase tests.

## K. Known Limitations

- Real tenant management (where a Global Admin could manage all tenants) is absent as it is not supported by the underlying schema.
- True Resource Quotas (e.g. 5GB max storage per month) are not tracked in the schema.
- No pagination added for `/api/v1/admin/users` as the number of users per tenant is assumed small enough for MVP (typically team size <100), but standard list fetching scales easily.
