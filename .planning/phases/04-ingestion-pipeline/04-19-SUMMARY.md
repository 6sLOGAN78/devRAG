---
phase: 04-ingestion-pipeline
plan: 19
subsystem: api
tags: [ingestion, parsing-log, task-status, embedding-check, isolation-matrix, leak-sweep, openapi]
requires:
  - phase: 04-18
    provides: chunk routes, write_rate_guard, matrix and leak-sweep builders
  - phase: 04-14
    provides: roll-up daemon that writes PipelineOperationLog dsl and progress_msg
provides:
  - GET /api/v1/datasets/{dataset_id}/ingestions/summary
  - GET /api/v1/datasets/{dataset_id}/ingestions and .../ingestions/{log_id}
  - POST /api/v1/datasets/{dataset_id}/embedding/check
  - GET /v1/task/status/{task_id}
  - ingestion_read_service, ingestion_api, seed_parse_artifacts
affects: [04-26 SPA ingestion views]
tech-stack:
  added: []
  patterns: [explicit DTO key lists, fixed plain error sentences by code, typed 409 where the one 404 would hide a reason]
key-files:
  created:
    - api/db/services/ingestion_read_service.py
    - api/apps/restful_apis/ingestion_api.py
    - test/integration/test_ingestion_read.py
    - test/testcases/test_ingestion_api.py
  modified:
    - api/apps/__init__.py
    - conf/routes.yaml
    - test/fixtures/route_policy_cases.json
    - api/apps/route_policy_gen.py
    - internal/common/route_policy_gen.go
    - test/helpers/fake_provider.py
    - test/helpers/ingest.py
    - test/testcases/_matrix_fixtures.py
    - test/testcases/test_phase3_isolation.py
    - test/testcases/test_response_leaks.py
    - web/openapi/openapi.json
    - web/src/interfaces/openapi.d.ts
    - .planning/DECISIONS.md
key-decisions:
  - "R-176: result key, plain errors, partial semantics, 409 model_unavailable, cancelled runs show live chunk count."
requirements-completed: []
duration: resumed session
completed: 2026-10-17
---

# Phase 4 Plan 19: Ingestion summary, runs, task status and model check Summary

Members can see how many documents are waiting, running, finished, failed or cancelled, read each parsing run with a plain typed error and redacted progress lines, look up a task, and managers can test the embedding model against the dimension the index was built for.

## Tasks

| Task | Commits | Result |
|------|---------|--------|
| 1 Read service | RED 80fafc1, GREEN 1580f6d | 19 integration tests against the real MySQL, index and loopback provider |
| 2 Handlers, five rows, e2e journey | RED 976ee34, GREEN 7c8a65a | five registry rows, `ingestion_bp`, 12 e2e journeys; stack rebuilt |
| 3 Matrix, isolation, leak sweep, types | c24c24c | builders, invokers, `sweep_ingestion_rows`, OpenAPI and TS types |
| Docs | fb4d016 | R-176 |

## Verification

- `pytest -m integration test/integration/test_ingestion_read.py`: 19 passed.
- `pytest -m e2e` for test_ingestion_api, test_cross_tenant_matrix, test_response_leaks, test_phase3_isolation, test_openapi: 198 passed.
- `run_tests.py -m unit`: 2046 passed, 3 skipped. `scripts/ci/run_all.py`: 7/7 gates (decisions 176 rows). `package.json` and lockfile untouched.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Embedding check answered the one 404 for an unavailable model**
- **Found during:** Task 2 e2e. `service_error_response` hides the reason for NOT_FOUND, so `model_unavailable` was not visible.
- **Fix:** `embedding_check` raises a typed 409 `model_unavailable` (also when `LLMBundle` raises NOT_FOUND). Recorded in R-176.
- **Commit:** 7c8a65a

**2. [Rule 1 - Bug] A cancelled run showed `chunk_count` 0 while its chunks were kept**
- **Fix:** for a cancelled entry with no stored count, `chunk_count` is the document's live `chunk_num`.
- **Commit:** 7c8a65a

**3. [Rule 3 - Blocking] Isolation table did not cover `/v1/task/status`**
- `PHASE3_PREFIXES` extended so the task row needs, and gets, an invoker. The embedding check row was added to `NORMAL_IS_REFUSED_ON_A_RESOURCE` and, with the three dataset read rows, to `ID_ROWS`. The check is invoked with `{"embd_id": null}` because the matrix sender drops an empty body.
- **Commit:** c24c24c

### Environment

The stack was down after a host restart (infra containers exited). Brought up with the `make up` compose command (cpu, elasticsearch, mail profiles) and `scripts/wait_stack.sh`; all services healthy. `vm.max_map_count` is 65530 but ES started and went healthy.

One integration run failed `test_a_finished_run_reports_its_counts_from_the_real_rollup` once while the stack executor was running, and passed on three reruns. Likely interference from the live task executor sharing the loopback provider or database; not reproduced.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register. T-04-19-01 (fixed sentences, detail only for provider_refused, JSON scan in e2e), -02 (visibility first, matrix builders for log and task ids), -03 (manage rule plus limiter), -04 (size at most 100, 3000 lines), -05 (task joined to its dataset and visibility rule) are covered.

## Self-Check: PASSED

Files exist; commits 80fafc1, 1580f6d, 976ee34, 7c8a65a, c24c24c, fb4d016 present.
