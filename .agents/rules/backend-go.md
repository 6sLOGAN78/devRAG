---
description: Rules for Go backend development
trigger:
  paths: ["internal/**/*.go", "cmd/**/*.go"]
---
# Go Backend Rules

When working on the Go backend for devRAG, adhere to the following standards:

1. **ORM Usage:** 
   - Use `gorm` for all database interactions.
2. **Layered Architecture:**
   - DAOs (Data Access Objects) live in `internal/dao/`.
   - Business logic lives in `internal/service/`.
   - HTTP Handlers live in `internal/handler/`.
3. **Error Handling:**
   - Handle errors gracefully. Return formatted error JSON responses to the frontend.
   - Log critical errors using the project's standard logger; do not use `panic` for expected runtime errors.
4. **Testing:**
   - Write unit tests for your services where possible.
