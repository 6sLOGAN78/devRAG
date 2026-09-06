# Testing (`tests/`)

Multi-layered testing strategy for DevRAG.

## Structure
- `e2e/`: Playwright end-to-end tests ensuring the frontend and backends integrate correctly.
- `integration/`: Go integration tests using `net/http/httptest` simulating API flows.
- `unit/`: Go and Python unit tests for isolated logic (like vector parsing).
- `fixtures/`: Sample PDFs and data used by tests.
