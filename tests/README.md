# Testing Suite (`/tests`)

This directory contains integration and end-to-end tests for **DevRAG**.

- **E2E Playwright**: UI testing against the React frontend.
- **Go Integrations**: Go `testing` suite testing the Gin Handlers, tenant isolation boundaries, and DAO operations.
- **Python Pipelines**: Verification scripts to ensure `deepdoc` parsing, chunking, embedding generation, and `Infinity` insertion accurately propagate from start to finish.
