---
phase: 04-ingestion-pipeline
plan: 17
subsystem: api
tags: [document-switch, doc_enabled_int, delete, pipeline-log, isolation-matrix, leak-sweep]
requires:
  - phase: 04-11
    provides: worker task-row re-check, document_switch reads
  - phase: 04-16
    provides: matrix resource_of, list rows with enabled, leak-sweep builders
provides:
  - POST /api/v1/datasets/{dataset_id}/documents/batch-update-status
  - document_service.set_documents_enabled
  - run-log rows removed with their documents (release_files)
affects: [04-26 SPA document table switch, Phase 5 retrieval (ANDs both flags)]
tech-stack:
  added: []
  patterns: [store the switch first and revert on index failure, two independent chunk flags]
key-files:
  created:
    - test/integration/test_document_switch.py
    - test/testcases/test_document_switch_flow.py
    - test/testcases/test_delete_chunks_flow.py
  modified:
    - api/db/services/document_service.py
    - api/db/services/file_service.py
    - api/apps/restful_apis/document_api.py
    - conf/routes.yaml
    - test/fixtures/route_policy_cases.json
    - test/helpers/accounts.py
    - test/testcases/_matrix_fixtures.py
    - test/testcases/test_response_leaks.py
    - api/apps/route_policy_gen.py
    - internal/common/route_policy_gen.go
    - web/openapi/openapi.json
    - web/src/interfaces/openapi.d.ts
    - .planning/DECISIONS.md
key-decisions:
  - "R-173: response shape {updated, enabled}, status strings 1/0, revert of the stored switch on index failure, run-log rows deleted inside release_files."
requirements-completed: []
duration: ~60min
completed: 2026-10-17
---

# Phase 4 Plan 17: Document search switch and clean deletion Summary

Whole documents can be switched in and out of search without losing any chunk's own choice, and deleting a document or dataset leaves no chunk, task row or run-log row behind, even with a worker still writing.

## Tasks

| Task | Commits | Result |
|------|---------|--------|
| 1 Failing tests | RED 6fe71af | 8 integration, 7 switch e2e, 4 delete e2e cases (19 total); `delete_accounts` removes `task` and `pipeline_operation_log` rows by recorded tenant. Failed for the right reason: `set_documents_enabled` missing |
| 2 Service, route, log cleanup, rebuild | GREEN 9ae3612, lint fix 9ca31da | Integration 8 pass (plus test_document_service 32 unchanged); e2e 11 pass after one rebuild |
| 3 Matrix and leak sweep | 54590db | builder and `sweep_status_rows`; 59 e2e pass; OpenAPI and TS types regenerated |
| Docs | d4ad934 | R-173 |

## Verification

- Stack rebuilt once (compose up -d --build with cpu, elasticsearch, mail profiles, then wait_stack); healthy.
- Integration: test_document_switch, test_document_service pass.
- E2E: test_document_switch_flow, test_delete_chunks_flow, test_cross_tenant_matrix, test_response_leaks, test_openapi pass. The delete-while-running case waits for the count to settle at zero and the executor logs no traceback.
- Unit suite 1966 passed, 3 skipped; `scripts/ci/run_all.py` 7/7; `go test ./internal/common/...` ok; `package.json` and lockfile untouched.
- `grep available_int api/db/services/document_service.py` prints nothing.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug in own test] Team-dataset test chunks had no index**
- **Found during:** Task 2
- **Issue:** `team_dataset_of` datasets have no index yet, so inserting test chunks failed.
- **Fix:** the test helper calls `create_idx` first (as `test/helpers/ingest.py::put_chunks` does).
- **Commit:** 9ae3612

**2. [Lint] Fixture imports redefined names (F811)**
- Aliased the shared fixtures the way `test_document_service.py` does. Commit 9ca31da.

### Plan wording

- `grep -n 'batch-update-status' web/src/constants/api-routes.generated.json` prints nothing: that file lists prefix routes only (the dataset-documents rows are covered by the `/api/v1/datasets` prefix), so the new path appears in `conf/routes.yaml`, `route_policy_gen.py`, `route_policy_gen.go` and `route_policy_cases.json`. `check_generated.py` exits 0.
- `snapshot_documents()` already carries `enabled` through the Phase 4 list rows, so it needed no change.
- The service takes `settings` first, per the Action text (the Behavior line omits it).
- The delete-while-running service code needed no change: the 04-11 task-row re-check already prevents orphans, and the new e2e proves it.

## Known Stubs

None.

## Threat Flags

None. T-04-17-01..06 are covered by the role integration tests, the sweep and matrix builder (one 404), the two-flag test, the delete-while-running e2e, the log-row count assertions and the revert test.

## Self-Check: PASSED

Files exist; commits 6fe71af, 9ae3612, 9ca31da, 54590db, d4ad934 present.
