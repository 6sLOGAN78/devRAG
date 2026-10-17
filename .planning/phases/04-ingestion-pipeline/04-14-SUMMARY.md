---
phase: 04-ingestion-pipeline
plan: 14
subsystem: ingestion
tags: [parse-route, cancel, reparse, rate-limit, e2e, route-registry, leak-sweep, cross-tenant]
requires:
  - phase: 04-10
    provides: authorize_parse, start_parse, cancel_parse
  - phase: 04-12
    provides: task executor container
  - phase: 04-13
    provides: parse config and document view
provides:
  - POST /api/v1/datasets/{dataset_id}/documents/parse (start, cancel, re-parse)
  - ingestion_service.parse_rate_guard
  - first end-to-end ingestion journey on the real stack
  - matrix builder and leak-sweep exerciser for the route
affects: [web parse button, later ingestion UI plans]
tech-stack:
  added: []
  patterns: [blueprint per concern in a new module, authorise on DB executor then work on DOCSTORE executor, per-tenant FixedWindowLimiter failing closed]
key-files:
  created:
    - api/apps/restful_apis/parse_api.py
    - test/testcases/test_parse_flow.py
    - test/integration/test_parse_rate.py
  modified:
    - api/apps/__init__.py
    - api/db/services/ingestion_service.py
    - conf/routes.yaml
    - test/fixtures/route_policy_cases.json
    - api/apps/route_policy_gen.py
    - internal/common/route_policy_gen.go
    - test/helpers/ingest.py
    - test/testcases/_matrix_fixtures.py
    - test/testcases/test_response_leaks.py
    - web/openapi/openapi.json
    - web/src/interfaces/openapi.d.ts
key-decisions:
  - "run 2 (cancel) is not rate limited; only run 1 spends a parse_rate ticket, so a user can always stop work"
  - "A rate-limit store outage is reported as queue_unavailable (503), the reason the plan specifies, and fails closed"
  - "Cancel and start both run in the DOCSTORE executor with a 60 s bound; authorisation and the rate ticket run in the DB executor"
requirements-completed: []
duration: ~2h (with an interruption)
completed: 2026-10-17
---

# Phase 4 Plan 14: Parse, cancel and re-parse route with the first end-to-end journey

One route turns an uploaded TXT into searchable chunks through the real stack, with confirmation for destructive re-parse, cancel that keeps indexed chunks, a per-tenant rate limit, and isolation and leak coverage.

## Tasks

| Task | Commits | Result |
|------|---------|--------|
| 1 Failing journey and rate guard tests | RED 1bf511e | 15 e2e tests + 2 integration tests written; first failure `parse answered 404` (route absent) |
| 2 Handler, registry row, guard, rebuild | GREEN 7ba7fa0 | 15 e2e and 2 integration tests pass on the rebuilt stack |
| 3 Matrix builder, leak sweep, OpenAPI types | aa597cf | 118 e2e tests pass (matrix, leaks, route enumeration, openapi) |

## Verification

- `uv run python -m pytest -m e2e test/testcases/test_parse_flow.py`: 15 passed (upload parses nothing, parse to run 3 with 40 chunks and totals equal to the index, 409 confirm_required with counts, confirmed re-parse gives the same count, cancel keeps chunks and a following parse finishes with 200 chunks, uploader/non-uploader/token, parse_unavailable, chunker_unavailable, already_running, all-or-nothing, ids_invalid, outsider 404, extra-field refusal, executor log has no Traceback).
- `uv run python -m pytest -m integration test/integration/test_parse_rate.py`: 2 passed.
- `uv run python -m pytest -m e2e test/testcases/test_cross_tenant_matrix.py test/testcases/test_response_leaks.py test/testcases/test_route_enumeration.py test/testcases/test_openapi.py`: 118 passed.
- `scripts/ci/check_generated.py` exit 0; `scripts/ci/run_all.py` 7/7 gates; no package file changed; `parse_api.py` imports no models or peewee.
- Nginx configs regenerated without change (the `/api/v1/datasets/` body-limit family already covers the route).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Matrix resource mapping did not know the parse path**
- **Found during:** Task 3
- **Issue:** `resource_of` mapped only paths ending in `/documents` to the documents snapshot, so the new row compared against the datasets snapshot.
- **Fix:** paths ending in `/documents/parse` map to `documents` too.
- **Files modified:** test/testcases/_matrix_fixtures.py
- **Commit:** aa597cf

**2. [Rule 1 - Bug in test design] Fake provider release_slow is permanent**
- **Found during:** Task 1
- **Issue:** `release_slow()` sets an event for good, so later `delay_ms` waits would return at once.
- **Fix:** the flow tests only reset `delay_ms = 0` and let in-flight calls finish.

### Notes

- The RED run first waited 120 s in a poll because the fixture did not check the parse status; the fixture now asserts 200 first so the RED failure is immediate (included in the RED commit).
- The stack was rebuilt once (compose `up -d --build` with the cpu, elasticsearch and mail profiles, then `scripts/wait_stack.sh`) because `make up` preflight fails on this host.

## Known Stubs

None.

## Threat Flags

None. T-04-14-01..06 mitigations are in place and tested: one 404 for invisible datasets (matrix), permission judged on the subject (member, uploader, token tests), 100-id cap and per-tenant limiter, server-decided confirmation, fixed messages checked by the leak sweep, `extra="forbid"` body.

## Self-Check: PASSED

Files exist (parse_api.py, test_parse_flow.py, test_parse_rate.py); commits 1bf511e, 7ba7fa0, aa597cf present.
