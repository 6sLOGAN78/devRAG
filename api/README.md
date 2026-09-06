# Python ML Backend (`api/`)

This directory contains the Python Quart/FastAPI backend responsible for ML operations, document parsing, embeddings, and chat generation. It operates alongside the Go API gateway.

## Structure
- `apps/`: Web application blueprints and HTTP routes.
- `db/`: Python database models (used mostly for analytics and background worker access).
- `services/`: Core Python business logic (e.g., executing agent tasks, processing parse jobs).
- `utils/`: Python utilities.

## Entrypoint
The server starts via `ragflow_server.py`, which boots up the Hypercorn asyncio server.
