# RBAC Contract

## Roles
- `owner`: Workspace creator; complete control over tenant configuration.
- `admin`: Privileged management; cannot delete tenant or revoke owner.
- `normal`: Standard member; creates and accesses shared resources.
- `invite`: Pending state; **denied access** to active tenant contexts and protected resource paths.

## Propagation
The authoritative source for roles is the `UserTenant` association in the database. 
- Go middlewares expose it securely via `c.Get("role")`. 
- Python decorators expose it securely via `g.role`.
Clients cannot spoof or override their resolved role by altering HTTP headers or JWTs. 

## Resource-Level Rules
Future resources (Datasets, Documents, Workflows) will utilize the resolved Tenant Context:
- `tenant_id` + `role` + `created_by` + `permission ("me", "team")`
to enforce discrete boundaries without re-implementing JWT or session evaluation.
