---
phase: 04-ingestion-pipeline
plan: 16
subsystem: api
tags: [document-detail, document-settings, routes, openapi, isolation-matrix, leak-sweep]
requires:
  - phase: 04-14
    provides: parse route, matrix resource_of
  - phase: 04-15
    provides: document_view, parser_config, pdf_pages
provides:
  - GET /api/v1/datasets/{dataset_id}/documents/{doc_id} (detail)
  - PATCH /api/v1/datasets/{dataset_id}/documents/{doc_id} (chunking settings)
  - document_service.update_document_settings, detail_view, change_settings_view
  - list handler on the Phase 4 rows (list_rows_view)
affects: [04-26 SPA document table and detail]
tech-stack:
  added: []
  patterns: [open-typed chunking values with service-side typed errors, one cached page count for splitting and detail]
key-files:
  created:
    - test/integration/test_document_settings.py
    - test/testcases/test_document_detail_flow.py
  modified:
    - api/apps/restful_apis/document_api.py
    - api/db/services/document_service.py
    - api/db/services/ingestion_service.py
    - conf/routes.yaml
    - test/fixtures/route_policy_cases.json
    - test/testcases/_matrix_fixtures.py
    - test/testcases/test_response_leaks.py
    - test/testcases/test_document_flow.py
    - test/testcases/test_parse_flow.py
    - api/apps/route_policy_gen.py
    - internal/common/route_policy_gen.go
    - web/openapi/openapi.json
    - web/src/interfaces/openapi.d.ts
key-decisions:
  - "R-169 to R-172 added to DECISIONS.md (the three 04-15 rows plus this plan's settings-route row)."
  - "Chunking values are typed open in the request model so a bad value is the service's typed parser_config_invalid with data.field, not a generic schema 400."
  - "A storage failure while counting pages for task splitting now yields one full-range task instead of a 503 (pdf_page_count reports None)."
requirements-completed: []
duration: ~70min
completed: 2026-10-17
---

# Phase 4 Plan 16: Document detail and settings routes Summary

The SPA contract for one document is now served over HTTP: the list returns the Phase 4 rows, GET returns the row plus chunking values and preview kind, and PATCH changes a single document's method and chunking values without re-chunking.

## Tasks

| Task | Commits | Result |
|------|---------|--------|
| 1 Page-count reuse and settings service | RED bee6ab9, GREEN 5276b43 | 10 integration cases; ingestion_service uses `pdf_page_count`, own copy removed |
| 2 Routes, list handler, pins, matrix, leak sweep, rebuild | e5ace59 | 12 e2e cases in test_document_detail_flow; matrix and leak sweep cover both rows |
| Docs | 437a790 | R-169..R-172 |

## Verification

- Integration: test_document_settings, test_ingestion_service, test_document_service: 60 passed (plan 04-10 tests unchanged).
- Stack rebuilt once (compose up -d --build with cpu, elasticsearch, mail profiles, then wait_stack); healthy.
- E2E: test_document_detail_flow, test_document_flow, test_upload_flow, test_parse_flow, test_cross_tenant_matrix, test_response_leaks: all pass.
- Unit suite 1965 passed, 3 skipped; `scripts/ci/run_all.py` 7/7 gates; `go test ./internal/common/...` ok; `web` `tsc --noEmit` clean; `package.json` and lockfile untouched.
- The PATCH e2e test asserts `run`, `progress`, `chunk_count` and the index count are identical before and after.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] test_parse_flow read the old `chunk_num` list key**
- **Found during:** Task 2
- **Issue:** `wait_run` and `doc_row` read list rows, which now use `chunk_count`.
- **Fix:** four assertions in `test/testcases/test_parse_flow.py` (a Phase 4 test) read `chunk_count`; the dataset row keeps `chunk_num`.
- **Commit:** e5ace59

**2. [Plan wording] The leak sweep had no `thumbnail` ban to relax**
- The ban lives in the `BANNED` sets of `test_document_flow.py` (list, relaxed for document rows) and `test_upload_flow.py` (upload response, kept narrow). `_leak_sweep.py` was not changed; it bans `status`/`source`, which rows no longer use.

**3. [Plan wording] Unknown method on PUT is `dataset_invalid`, not `parser_invalid`**
- The Phase 3 behaviour is `dataset_invalid`; the e2e test pins that existing answer ("keeps"). Not changed.

**4. [Scope] API-token subject e2e**
- The token case that must be refused (neither uploader nor creator) is pinned at service level in `test_document_settings`; at e2e level a member cannot create a dataset in the owner's workspace with the available fixtures, so the e2e test covers the token's allowed paths and the leak sweep exercises the token on both rows.

## Decisions needing rows

None outstanding; R-169..R-172 recorded in a separate docs commit. No Phase 3 test was changed or weakened.

## Known Stubs

None.

## Threat Flags

None. T-04-16-01 (non-uploader or token write) is covered by `can_remove_document` with `scope.subject`, integration test per role and the sweep; T-04-16-02 (detail polling) by the per-(doc, hash) page-count cache and the storage executor with a 20 s deadline.

## Notes for follow-up

- The SPA (`web/src/services/document-service.ts`) still reads `chunk_num` from list rows; plan 04-26 moves it to `chunk_count` and updates the web in-memory server.

## Self-Check: PASSED

Files exist; commits bee6ab9, 5276b43, e5ace59, 437a790 present.
