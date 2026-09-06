# Tenant Context Contract

## Purpose
Establishes a unified security boundary defining how authenticated identities are mapped to authorized tenants. All future dataset, document, and chat operations rely on this security context to enforce multi-tenant isolation.

## Membership Truth
A user can only operate within a tenant if a valid `UserTenant` association exists for their `user_id`, AND their role is NOT `invite`. `tenant_id` claims passed by clients in headers or JWTs are explicitly **untrusted** until validated against the database.

## Tenant Selection
- **Implicit:** If no explicit tenant is requested, the system automatically defaults to the first `UserTenant` association the user holds where role != `invite`.
- **Explicit:** Clients may request a specific tenant using the `X-Tenant-ID` HTTP header. 

## Cross-Stack Consistency
Both the Go Gin Gateway and Python Quart API natively enforce the exact same boundary rules:
- **Go:** Middleware intercepts, asserts `UserTenant` validity, and stores trusted values in Gin's context via `c.Set("user_id")`, `c.Set("tenant_id")`, and `c.Set("role")`.
- **Python:** The `@require_auth` decorator evaluates the exact same Redis Session and MySQL `UserTenant` criteria, making trusted values available to ML endpoints globally via Quart's `g.user_id`, `g.tenant_id`, and `g.role`.

## Security States
- **401 Unauthorized:** Occurs when JWT signature is invalid, token is expired, or the required Redis session (`session:{user_id}`) is missing/inactive.
- **403 Forbidden:** Occurs when a user successfully authenticates but attempts to access an `X-Tenant-ID` they lack `UserTenant` association with, attempts to access an `invite` membership, or if they have zero tenant memberships.
