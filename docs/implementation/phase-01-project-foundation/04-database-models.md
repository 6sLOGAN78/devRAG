## Objective
Define the core relational database schema (Tenants, Users, Datasets) and implement ORM models in Python (Peewee/SQLAlchemy) and Go (GORM).

## Why Now?
The DB schema is the backbone of the application. Both gateways and services rely on standard user/tenant definitions.

## Dependencies
- 03-configuration-management

## Implementation Tasks
- [ ] Define SQL migrations for `tenant` and `user` tables.
- [ ] Implement Go ORM models in `internal/dao/models.go`.
- [ ] Implement Python ORM models in `api/db/db_models.py`.
- [ ] Create DB connection initialization logic in both Go and Python (using config from subphase 03).

## Components
- Database connection pool.
- ORM entities.

## Files
- `internal/dao/db.go`
- `internal/dao/models.go`
- `api/db/db_models.py`
- `api/db/connection.py`

## Interfaces
N/A

## Data Changes
Creates `tenant` and `user` tables.
Columns: `id`, `email`, `password_hash`, `tenant_id`, `role`, `created_at`.

## Data Flow
App -> ORM -> MySQL

## Testing
- Integration test in Go: Insert and retrieve a user.
- Integration test in Python: Insert and retrieve a tenant.

## Deliverable
Database schemas and ORM mappings accessible from both Go and Python.

## Definition of Done
- Migrations apply successfully.
- Go and Python can perform CRUD on the `user` table.

## Next Subphase
Phase 02 (Gateway & Auth) - 01-go-gin-gateway