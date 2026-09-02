# Phase 05: Ingestion Pipeline & Task Synchronization

## Phase Objective
Build the asynchronous worker system that connects the Document Upload API to the Python DeepDoc parser via task queues.

## Why This Phase Comes Here
Parsing is slow. Uploads must be async. We need a task worker (Syncer) to orchestrate the pipeline.

## Dependencies
Depends on:
- Phase 03 (Upload), Phase 04 (DeepDoc)

Required by:
- Phase 06 (Vector Search)

## Phase Architecture
Go creates tasks in MySQL/Redis. A Go `syncer` daemon dispatches tasks to Python worker APIs, polling for status updates.

## Subphase Order
01-task-queue-models -> 02-go-syncer-worker -> 03-python-task-executor -> 04-frontend-progress-ui

## Phase Deliverable
A complete background ingestion pipeline. When a user uploads a file, it is automatically processed in the background, and status updates appear in the UI.

## Phase Definition of Done
- Uploading a document triggers a background job.
- Job executes DeepDoc parsing.
- Status changes from UNSTART -> RUNNING -> SUCCESS.

## What NOT To Build Yet
Vector insertion (done in Phase 06).

## Next Phase
Phase 06: Core RAG & Vector Engine
