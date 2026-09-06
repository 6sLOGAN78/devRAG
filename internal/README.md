# Go Core Logic (`internal/`)

This directory houses the private Go application code. It follows the standard Handler -> Service -> DAO architecture.

## Structure
- `api/`, `handler/`: Gin HTTP route handlers.
- `service/`: Core business logic and validations.
- `dao/`: Data Access Object layer; handles all MySQL and Redis queries.
- `router/`: Gin router and middleware initialization.
- `syncer/`: The Go background worker that syncs tasks between the database and the Python ML backend.
- `storage/`: Object storage adapters (MinIO/S3).
