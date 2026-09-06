# Phase 03: Knowledge Base & Document Management

## Phase Objective
Build the Dataset (Knowledge Base) CRUD and Document Upload pipelines, integrating with MinIO and the React frontend.

## Why This Phase Comes Here
Before we can parse or retrieve data, users need a UI and API to create Knowledge Bases and upload documents into them.

## Dependencies
Depends on:
- Phase 02 (Auth & Gateway)

Required by:
- Phase 04 (DeepDoc Parsing)

## Phase Architecture
Introduces MinIO object storage integration for raw file uploads. React frontend UI is initialized to manage Datasets and upload files.

## Subphase Order
01-dataset-crud-api -> 02-document-upload-api -> 03-frontend-auth-and-layout -> 04-frontend-knowledge-ui

## Phase Deliverable
A working UI where users can log in, create a knowledge base, and upload PDFs/Word docs which are saved to MinIO.

## Phase Definition of Done
- Datasets and Documents are saved in DB with `tenant_id`.
- Uploaded files are successfully pushed to MinIO.
- Frontend renders Dataset list and handles file uploads.

## What NOT To Build Yet
Document parsing, OCR, or chunking.

## Next Phase
Phase 04: Deep Document Parsing (DeepDoc)

## Distributed Coordination Requirements
- **Dataset APIs**: Must use `RedisDistributedLock` in Dataset API Service to control concurrent dataset modifications.
- **Knowledge Compilation**: Must use locks (`merge_lock`) for dataset compilation and structure compilation (`dataset_nav.py` and `structure.py`).