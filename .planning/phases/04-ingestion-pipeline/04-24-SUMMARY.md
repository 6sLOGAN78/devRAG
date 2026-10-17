---
phase: 04-ingestion-pipeline
plan: 24
subsystem: web
tags: [services, mappers, blob, path-builders, chunk_count]
requires:
  - phase: 04-20
    provides: page image and content routes
  - phase: 04-23
    provides: per-area locales and test-server seam
provides:
  - "document-service: parseDocuments, setDocumentsEnabled, getDocument, updateDocumentSettings, confirmCountsOf, extended DocumentView"
  - "chunk-service: listChunks, createChunk, updateChunk"
  - "ingestion-service: getIngestionSummary, listIngestionLogs, getIngestionLog, getTaskStatus, checkEmbedding"
  - "page-service: fetchPageImage, fetchTextPreview, downloadDocument, PreviewTypeError"
  - "dataset-service: DatasetDetailView.parserConfig, updateDatasetChunking"
  - "app-paths: datasetLogsPath, chunkPath, documentViewerPath and route constants"
affects: [04-25, 04-26, 04-28, 04-30, 04-32]
tech-stack:
  added: []
  patterns: [explicit field mappers, status-only blob error classification, inline axios adapter service tests]
key-files:
  created:
    - web/src/services/chunk-service.ts
    - web/src/services/ingestion-service.ts
    - web/src/services/page-service.ts
    - web/src/services/chunk-service.test.ts
    - web/src/services/ingestion-service.test.ts
    - web/src/services/page-service.test.ts
    - web/src/constants/app-paths.test.ts
  modified:
    - web/src/constants/api-paths.ts
    - web/src/constants/app-paths.ts
    - web/src/services/document-service.ts
    - web/src/services/document-service.test.ts
    - web/src/services/dataset-service.ts
    - web/src/services/dataset-service.test.ts
    - .planning/DECISIONS.md
key-decisions:
  - "R-178: chunk_count preferred with chunk_num fallback; vetting limits; confirmCountsOf in document-service.ts"
requirements-completed: []
duration: ~25min
completed: 2026-10-17
---

# Phase 4 Plan 24: SPA Phase 4 service layer Summary

Every Phase 4 API call now has one typed service function with an explicit-field mapper, `silent: true`, the contract timeouts, and vetted output (two thumbnail prefixes, JPEG/PNG blobs only), plus the three screen path builders.

## Tasks
1. Paths, services, mappers (commit ca57b20): new `api-paths.ts` builders resolved through the generated prefix routes; four services; `DatasetDetailView.parserConfig` and `updateDatasetChunking`; `datasetLogsPath`, `chunkPath`, `documentViewerPath` with `DATASET_LOGS_ROUTE`, `CHUNK_ROUTE`, `DOCUMENT_VIEWER_ROUTE`; R-178.

## Verification
- Web unit project: 63 files, 1193 tests pass; `tsc --noEmit` exits 0.
- No `dangerouslySetInnerHTML` or `createObjectURL` under `web/src/services`; `package.json` and lockfile unchanged.

## chunk_count status
`toDocument` reads `chunk_count` and falls back to `chunk_num` when absent. The SPA chunk count is therefore correct for the real API now, and the web in-memory test server (still emitting `chunk_num`) keeps working. `DocumentView.chunkNum` is kept (same number as `chunkCount`). The test-server rows can be switched to `chunk_count` by the screen plan that owns the document handler area (04-26); nothing else is required for correctness. The dataset row (`chunk_num` on datasets) is unchanged by the backend.

## Deviations from Plan
- **[Process] TDD order:** services and tests were written together and committed once; the RED run was not committed separately.
- **[Plan wording] `confirmCountsOf`** was planned for `errors.ts` ("Task 3"), which does not exist; it is exported from `document-service.ts` (R-178). Later plans import it from there.
- **[Plan wording] `getTaskStatus` and `checkEmbedding`** were added to `ingestion-service.ts` (the plan names the paths but no function); `taskStatusPath` resolves under the python `/v1/` prefix.
- The existing document-service test's `expectedView` gained the new fields (Phase 3 assertions on "0%" and "Not started" are untouched and pass).

## Known Stubs
None.

## Threat Flags
None.

## Self-Check: PASSED
