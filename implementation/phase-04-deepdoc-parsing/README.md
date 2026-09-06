# Phase 04: Deep Document Parsing (DeepDoc)

## Phase Objective
Implement the core AI vision and text extraction pipelines in Python to intelligently parse complex documents (PDFs, Tables).

## Why This Phase Comes Here
Before we can embed chunks into the Vector DB, we must extract and intelligently chunk the raw files stored in MinIO.

## Dependencies
Depends on:
- Phase 03 (Documents in MinIO)

Required by:
- Phase 05 (Ingestion & Sync)

## Phase Architecture
A pure Python data science module utilizing PyTorch, PaddleOCR, and YOLOv8 to reconstruct document structures.

## Subphase Order
01-deepdoc-interfaces -> 02-ocr-engine -> 03-layout-recognition -> 04-table-structure -> 05-chunking-strategies

## Phase Deliverable
A Python module capable of taking a PDF file and returning structured, layout-aware text chunks and table data.

## Phase Definition of Done
- Given a complex PDF, DeepDoc outputs clean Markdown/JSON chunks.
- Tables are reconstructed.
- Headers and paragraphs are separated.

## What NOT To Build Yet
Task queues or worker daemons (that is Phase 05). Vector embeddings (Phase 06).

## Next Phase
Phase 05: Ingestion Pipeline & Task Sync
