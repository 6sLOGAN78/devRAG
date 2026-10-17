---
phase: 04-ingestion-pipeline
plan: 18
subsystem: api
tags: [chunks, embed-before-write, doc_store, isolation-matrix, leak-sweep, openapi]
requires:
  - phase: 04-17
    provides: document switch (doc_enabled_int), matrix and leak-sweep builders
  - phase: 04-11
    provides: build_row, chunk id grammar, settle_totals
provides:
  - GET/POST /api/v1/datasets/{dataset_id}/documents/{doc_id}/chunks
  - PATCH /api/v1/datasets/{dataset_id}/documents/{doc_id}/chunks/{chunk_id}
  - chunk_service (list_chunks, create_chunk, update_chunk, chunk_dto)
  - ingestion_service.write_rate_guard, LLMBundle.token_limit, chunk_doc.manual_row
  - loopback provider embed_mode switch
affects: [04-26 SPA chunk views, Phase 5 retrieval (chunk flags and origin)]
tech-stack:
  added: []
  patterns: [embed first then one engine operation, drop a late embedding instead of writing it, check the boolean of every doc-store update]
key-files:
  created:
    - api/db/services/chunk_service.py
    - api/apps/restful_apis/chunk_api.py
    - test/integration/test_chunk_service.py
    - test/testcases/test_chunk_flow.py
    - .planning/phases/04-ingestion-pipeline/deferred-items.md
  modified:
    - api/db/services/ingestion_service.py
    - api/db/services/llm_service.py
    - rag/svr/chunk_doc.py
    - api/apps/__init__.py
    - conf/routes.yaml
    - test/fixtures/route_policy_cases.json
    - test/helpers/fake_provider.py
    - test/testcases/_matrix_fixtures.py
    - test/testcases/test_response_leaks.py
    - api/apps/route_policy_gen.py
    - internal/common/route_policy_gen.go
    - web/openapi/openapi.json
    - web/src/interfaces/openapi.d.ts
    - .planning/DECISIONS.md
key-decisions:
  - "R-174: request names follow docs (content_with_weight), responses say text; list uses size and available=0|1."
  - "R-175: embed first, one update_by_query for text, tokens, vector and origin; update result checked; late embedding dropped after 40 s."
requirements-completed: []
duration: ~2h
completed: 2026-10-17
---

# Phase 4 Plan 18: Chunk list, add, edit and switch Summary

Members can read a document's chunks with their place on the page, add a chunk by hand, correct a chunk's text and switch single chunks out of search; text is embedded before anything is written, so a provider failure leaves the previous text and vector untouched.

## Tasks

| Task | Commits | Result |
|------|---------|--------|
| 1 Chunk service | RED 5b9e319, GREEN 98d07ad | 24 integration tests (the plan asked for 14) against the real index, MySQL and the loopback provider. RED failed on the missing module |
| 2 Handlers, rows, journeys, rebuild | cc20cd4 | three registry rows, `chunk_bp`, 11 e2e journeys; stack rebuilt once |
| 3 Matrix, leak sweep, types | 5b4d229 | `snapshot_chunks`, three builders, `sweep_chunk_rows`; OpenAPI and TS types regenerated |
| Docs | bfa3769 | R-174, R-175 |

## Verification

- Stack rebuilt once (compose up -d --build with cpu, elasticsearch, mail profiles, then wait_stack): all services healthy.
- `pytest -m integration test/integration/test_chunk_service.py`: 24 passed.
- `pytest -m e2e test/testcases/test_chunk_flow.py`: 11 passed (includes provider refuse, rate limit, never-answers, D-26, parse_running, roles, id grammar, private dataset).
- `pytest -m e2e test_cross_tenant_matrix.py test_response_leaks.py test_openapi.py`: 65 passed.
- `test/unit_test`: 1969 passed, 3 skipped. `scripts/ci/run_all.py` 7/7. `go test ./internal/common/...` ok. `check_generated.py` and `check_decisions.py` (175 rows) pass. `package.json` and lockfile untouched.
- Acceptance greps: `sleep(` absent from the new test files; in `chunk_service.py` the `encode(` call (line 229, in `_embed`) comes before the `insert(` and `update(` calls in `create_chunk` and `update_chunk`; `chunk_api.py` imports no models or peewee.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] A late embedding could be written after the handler had answered "timed out"**
- **Found during:** Task 2 (reasoning about the 45 s handler deadline against the driver's 30 s timeout and 3 retries)
- **Issue:** `run_blocking` cannot stop the worker thread; a retry that succeeded after the 504 would still write the chunk.
- **Fix:** `chunk_service.WRITE_DEADLINE_SECONDS = 40`; an embedding that finishes later is dropped with `provider_timeout` before any write. Integration test covers it by shrinking the deadline. Recorded in R-175.
- **Files:** api/db/services/chunk_service.py, test/integration/test_chunk_service.py. **Commit:** cc20cd4

**2. [Rule 2 - Missing critical] Update result checked, edit done as one engine operation**
- The 04-17 lesson applied: `DocStoreConnection.update` returning False is refused as 503 `index_unavailable`; tests with a store whose `update` returns False and whose `insert` reports failed ids prove nothing changes. The edit uses `update_by_query` (not a re-insert of a fetched row) so a concurrent document switch's `doc_enabled_int` is never overwritten by a stale copy.

**3. [Rule 3 - Blocking] `LLMBundle.token_limit`**
- The embedding driver silently truncates over-long input, so `chunk_too_long` needs the limit first; a read-only property was added to the bundle (commit 98d07ad).

### Plan wording

- `manual_row` was added to `rag/svr/chunk_doc.py` (the plan names `MANUAL_ORDER` there but it did not exist); it reuses `build_row`.
- `api/utils/blocking.py` needed no change (`PROVIDER_EXECUTOR` already exists).
- `grep documents/{doc_id}/chunks web/src/constants/api-routes.generated.json` prints nothing: that file lists prefix routes only; the rows appear in `conf/routes.yaml`, both generated policy files and the route-policy cases (same as 04-17).
- The e2e file was written after the handler (service-layer RED was shown; the e2e RED was not run separately).
- The e2e journey for "a token is judged as its subject" asserts only the owner-token success: a member's API token is pinned to the member's own workspace (404 for the team dataset), so the forbidden-token case is proven in the integration test (owner token, document of another uploader, dataset of another creator: FORBIDDEN).
- The matrix seeds the chunks into the existing second team document (`a_parsed_document`) rather than adding a document, to keep the object count the upload matrix asserts.

### Decisions needing rows

Both recorded: R-174 (names and shapes), R-175 (embed-before-write, deadline, rate counting).

## Deferred Issues

`test/testcases/test_phase3_isolation.py::test_every_phase3_row_has_an_invoker` and its companion (marked `unit`, run only with `-m unit`) fail since 04-14: Phase 4 rows (parse, document detail and patch, batch-update-status) have no `INVOKERS` entry, and the three new chunk rows add to the same gap. Logged in `deferred-items.md`; not in `test/unit_test`.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register. T-04-18-01 (role and token tests), -02 (dataset visibility first, dataset id on every engine call, chunk id grammar, matrix builders), -03 (byte-for-byte comparison after refused edits, deadline drop), -04 (tokenized keywords, 128-character cap, size cap), -05 (shared per-tenant window, length and token checks before the provider call), -07 (bundle_error scrubbing, sweep scan) are covered.

## Self-Check: PASSED

Files exist; commits 5b9e319, 98d07ad, cc20cd4, 5b4d229, bfa3769 present.

## Post-plan fix

Commit d13ec02 added `INVOKERS` entries in `test/testcases/test_phase3_isolation.py` for the seven Phase 4 rows (parse, document detail and patch, batch-update-status, three chunk rows), closing the deferred guard-test failure. Parse uses run 2 (cancel) so the permitted call starts no work. The five uploader-or-admin writes joined `NORMAL_IS_REFUSED_ON_A_RESOURCE`. Strangers, random-id and foreign-token cases all answered the one 404; no wrong cross-tenant answer found. 95 isolation tests, 58 matrix tests, 2041 unit tests and 7/7 CI gates pass.
