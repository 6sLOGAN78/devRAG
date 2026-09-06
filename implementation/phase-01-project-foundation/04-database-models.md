# 04 - Core Database Models & Dual-ORM Synchronization

## Objective
Define the foundational database tables (`Tenant` and `User`) and implement ORM representations in both Go (GORM) and Python (Peewee).

## Production Requirements
RAGFlow is natively **Multi-Tenant**. The `tenant_id` is the absolute boundary for RBAC and data isolation.
- Every business table in the future will require a `tenant_id`.
- Python and Go MUST have identical ORM struct/class mappings for the same tables.

### Table: `Tenant`
Represents an organization or workspace.
- `id` (VARCHAR/UUID, Primary Key)
- `name` (VARCHAR)
- `llm_id` (Default LLM configuration for the workspace)
- `created_at` (TIMESTAMP)

### Table: `User`
Represents a global identity.
- `id` (VARCHAR/UUID, Primary Key)
- `email` (VARCHAR, Unique)
- `password_hash` (VARCHAR)
- `nickname` (VARCHAR)

### Table: `UserTenant`
The RBAC mapping table (Many-to-Many).
- `user_id` (FK to User)
- `tenant_id` (FK to Tenant)
- `role` (Enum: `owner`, `admin`, `normal`, `invite`)

## Implementation Tasks
- [ ] Create Go GORM structs in `internal/dao/models.go` with strict `gorm:"column:tenant_id"` tags.
- [ ] Create Python Peewee classes in `api/db/db_models.py` mapping to the same schema.
- [ ] Implement database connection pooling logic in Go (`internal/dao/db.go`).
- [ ] Implement database connection pooling logic in Python (`api/db/connection.py`).
- [ ] Set up an automated migration script (or use GORM's AutoMigrate/Peewee's create_tables for development).

## Deliverable
Dual-language ORM synchronization where both Go and Python can read/write users and tenants identically.
