---
phase: 04-ingestion-pipeline
plan: 20
subsystem: api
tags: [pdf, page-image, content-serving, text-preview, etag, temp-cache, isolation-matrix, leak-sweep, openapi]
requires:
  - phase: 04-19
    provides: ingestion read routes, matrix and leak-sweep builders
  - phase: 04-15
    provides: pdf_pages page-count cache, document detail preview kind
provides:
  - GET /api/v1/datasets/{dataset_id}/documents/{doc_id}/pages/{n}/image
  - GET /api/v1/datasets/{dataset_id}/documents/{doc_id}/content (bytes, or format=text)
  - page_service, PdfFileCache, PDF_EXECUTOR, page_api
affects: [04-26 SPA document viewer and inspector]
tech-stack:
  added: []
  patterns: [bounded hash-named temp-file cache, lock-serialised generator pump closed in finally, fixed type map by stored extension]
key-files:
  created:
    - api/db/services/page_service.py
    - api/apps/restful_apis/page_api.py
    - test/integration/test_page_service.py
    - test/testcases/test_page_flow.py
  modified:
    - api/db/services/pdf_pages.py
    - api/utils/blocking.py
    - api/utils/reasons.py
    - rag/parsers/txt.py
    - api/apps/__init__.py
    - conf/routes.yaml
    - test/fixtures/route_policy_cases.json
    - test/unit_test/test_handler_support.py
    - test/testcases/_matrix_fixtures.py
    - test/testcases/test_phase3_isolation.py
    - test/testcases/test_response_leaks.py
    - api/apps/route_policy_gen.py
    - internal/common/route_policy_gen.go
    - web/openapi/openapi.json
    - web/src/interfaces/openapi.d.ts
    - .planning/DECISIONS.md
key-decisions:
  - "R-177: JPEG zoom 3 via rasterize_page, content-hash ETag, fixed 2-thread PDF executor, 4-file/400 MiB temp cache, inline only for PDF/PNG/JPEG, HTML never text/html."
requirements-completed: []
duration: one session
completed: 2026-10-17
---

# Phase 4 Plan 20: Page images, original file and text preview Summary

A member can load any page of a stored PDF as a JPEG that lines up with the parser's boxes, open or download the original file safely, and read a decoded preview of text-like files.

## Tasks

| Task | Commits | Result |
|------|---------|--------|
| 1 Page service, PDF executor, temp cache | RED 14c1220, GREEN 3188e8e | 17 integration tests against the real MySQL and MinIO |
| 2 Handlers, two registry rows, e2e flow; stack rebuilt | RED 1822cc8, GREEN fc75dda | 15 e2e journeys on the rebuilt stack |
| 3 Matrix, isolation, leak sweep, types | 490d95d | builders, invokers, `sweep_page_rows`, OpenAPI and TS types, R-177 |

## Verification

- `pytest -m integration test/integration/test_page_service.py`: 17 passed.
- `pytest -m e2e test_page_flow.py`: 15 passed. Cross-tenant matrix, leak sweep, OpenAPI and isolation e2e: all passed (209 plus 119).
- `run_tests.py -m unit`: 2048 passed, 3 skipped. `scripts/ci/run_all.py`: 7/7 gates (177 decision rows). `package.json` and lockfile untouched.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Isolation table assumed a JSON success body**
- `succeeded()` in `test_phase3_isolation.py` called `resp.json()` on every 200. A JPEG or PDF body made it raise. A non-JSON 200 now counts as served.
- **Commit:** 490d95d

**2. [Rule 3 - Blocking] Matrix world needed real documents**
- The seeded documents were magic-byte stubs that pdfium cannot open. `upload_file` now uploads a unique real one-page PDF, and a `.txt` document `a_text_document` was added to the team dataset (object-count assertion 3 to 4). Its id and name are in `a_identifiers`.
- **Commit:** 490d95d

### Plan wording adjusted

- `PDF_EXECUTOR` stays at 2 workers: `ThreadPoolExecutor` has no public resize, and pdfium is serialised by one lock, so `ingest.pdf_render_threads` is not applied to it (recorded in R-177).
- The content-type map is an explicit table keyed by stored extension rather than derived from `ALLOWED_MIME_BY_EXT` (a set of accepted upload types, unordered and including `text/html`); the result is deterministic and never HTML.
- `rag/parsers/txt.py` gained a public `decode_text` wrapper so the preview shares the parser's decoding.
- Image e2e uses uploaded (not parsed) PDFs: the route does not depend on parsing.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register. T-04-20-01 (attachment except PDF/PNG/JPEG, nosniff, CSP sandbox, e2e asserts), -02 (visibility first, matrix builders), -03 (2-thread executor, 30 s deadline, fixed zoom), -04 (4 files, 400 MiB, hash names, 0700), -05 (`safe_filename`, `filename*`), -06 (no URL token), -07 (about 1 MiB read for text, chunked stream) are covered.

## Self-Check: PASSED

Files exist; commits 14c1220, 3188e8e, fc75dda, 490d95d present.
