---
name: add-new-api-endpoint
description: Use this skill when the user asks to add a new API endpoint in the Go or Python backend.
---
# Adding a New API Endpoint

When tasked with adding a new API endpoint, you MUST follow these exact steps to maintain architectural consistency:

## Step 1: Database Layer (DAO)
- Determine if the endpoint needs to read/write data.
- If yes, locate the appropriate DAO file (in `internal/dao/` for Go, or `api/db/` for Python).
- Write a clean, parameterized query function. **Never write SQL in the controller.**
- Ensure the query filters by `tenant_id` if it involves business data.

## Step 2: Business Logic Layer (Service)
- Locate or create a service file (in `internal/service/` for Go, or `api/db/services/` for Python).
- Write the business logic. The service should call the DAO and handle things like permission validation or quota checking.

## Step 3: API Layer (Handler/Controller)
- Write the HTTP handler.
- The handler's ONLY job is to parse the incoming HTTP request (JSON body, query params), call the Service layer, and format the HTTP response.
- Apply authentication middleware (e.g., `@login_required`).

## Step 4: Routing
- Register the newly created handler in the router file (e.g., `internal/router.go` for Go).

## Step 5: Documentation
- Update the relevant markdown files in `ragflow-docs/04-api/` to reflect the new endpoint.
