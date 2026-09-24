# Go Business Logic & Gateway (`/internal`)

The `internal` directory contains all proprietary Go code for the **DevRAG** API Gateway. This code enforces strict tenant isolation, authentication, and fast HTTP routing before handing off heavy ML tasks to the Python backend.

## Directory Structure

- **`config/`**: Parses `service_conf.yaml` and sets up the typed Go configuration structs.
- **`dao/`**: Data Access Objects using GORM. Defines the single source of truth for the MySQL database schema and provides methods for database operations.
- **`handler/`**: Gin HTTP handlers. They parse requests, validate input, extract tenant context, and proxy to services.
- **`middleware/`**: Request interceptors for Authentication (JWT), Rate Limiting (Redis), Logging, and Tenant Context extraction.
- **`router/`**: Defines the API routes (`/api/v1/*`) and attaches middleware to specific route groups.
- **`service/`**: Core business logic (e.g., TenantLLM resolution, Task execution, Canvas orchestrator).
- **`syncer/`**: Background worker pool that polls MySQL tasks and dispatches them to the Python ML engine.
