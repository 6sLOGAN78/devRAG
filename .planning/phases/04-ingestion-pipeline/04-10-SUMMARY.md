---
phase: 04-ingestion-pipeline
plan: 10
subsystem: ingestion
tags: [tasks, parse, reparse, cancel, totals, mysql, valkey, elasticsearch]
requires:
  - phase: 04-04
    provides: DocStoreConnection.stats with sum_field
  - phase: 04-07
    provides: TaskQueue (ping, enqueue), get_queue
  - phase: 04-08
    provides: pdf.count_pages
provides:
  - api/db/services/task_service.py (split_pages, task_digest, TaskContext, Claim, load_task_context, claim_attempt, refund_attempt, set_progress, mark_task_done, mark_task_failed, task_is_current, tasks_of)
  - api/db/services/ingestion_service.py (authorize_parse, start_parse, cancel_parse, fail_documents, chunk_counts, ParseStarted, ChunkCounts)
  - api/db/services/totals_service.py (settle_totals)
  - common/ingest_codes.py additions (queue_unavailable failure code, LOG_RUNNING/DONE/FAILED/CANCELLED)
affects: [04-12, 04-14, worker executor, parse routes]
tech-stack:
  added: []
  patterns: [guarded UPDATE for the attempt counter, counters set to index truth, check-all-then-change, hand-stamped update_time]
key-files:
  created:
    - api/db/services/task_service.py
    - api/db/services/ingestion_service.py
    - api/db/services/totals_service.py
    - test/unit_test/test_task_split.py
    - test/integration/test_task_service.py
    - test/integration/test_totals_service.py
    - test/integration/test_ingestion_service.py
  modified:
    - common/ingest_codes.py
key-decisions:
  - "Start refuses in a fixed order (not found, permission, parseable, chunker, model, running) across all ids before any state changes; then the confirmation rule; then a queue ping; PDF page counts are read before the dataset lock is taken"
  - "A second not-running check is made under the dataset lock before the index is pruned, and a third on the locked rows inside the transaction, so two racing starts cannot delete chunks of a running document"
  - "Documents are pruned from the index only when their chunk_num is above zero; chunk_counts asks the index only for those"
  - "cancel_parse settles totals only for documents it actually cancelled; an index outage there is logged, not raised, because the cancel already committed"
  - "fail_documents is public so the worker plan can reuse it for other failure codes"
  - "queue_unavailable is a failure code but not terminal"
patterns-established:
  - "Integration tests that use the queue take a per-test prefix and group and assert no key with that prefix remains"
requirements-completed: []
duration: ~55min
completed: 2026-10-17
---

# Phase 4 Plan 10: Task rows, parse/cancel/re-parse and settle-to-truth totals

The database side of ingestion: 0-based page-range task rows, an atomic attempt counter, start/cancel/re-parse with the confirmation rule and the index-truth counter repair, proven against the real MySQL, Elasticsearch, MinIO and Valkey.

## Tasks

| Task | Commits | Result |
|------|---------|--------|
| 1 Task rows, digest, attempts, totals | RED 9b27264, GREEN 72383b5 | 16 unit + 8 integration tests pass |
| 2 Start, cancel, re-parse | RED 1e58035, GREEN a48438c | 18 integration tests pass |

## Verification

- `uv run python -m pytest test/unit_test/test_task_split.py`: 16 passed (six split cases, digest sensitivity, codes).
- `uv run python -m pytest -m integration test/integration/test_task_service.py test/integration/test_totals_service.py test/integration/test_ingestion_service.py`: 26 passed.
- Full unit suite: 1888 passed, 3 skipped. `scripts/ci/run_all.py`: 7/7 gates.
- No `quart` import in the three services; `git status` shows no change under `api/db/models` or migrations (no schema change, D-20).
- Teardown of the ingestion tests asserts no Valkey key with the test prefix remains. After the run `task` and `pipeline_operation_log` hold zero rows.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Test fixtures: module-scoped `llm` vs function-scoped `settings`**
- **Found during:** Task 2
- **Issue:** the per-test queue prefix needs a function-scoped `settings`, but the reused `llm` fixture is module-scoped and depends on `settings`.
- **Fix:** `test_ingestion_service.py` defines its own function-scoped `llm` and `registry` fixtures. The registry also deletes the `task` and `pipeline_operation_log` rows of its accounts, which account cleanup does not.
- **Commit:** a48438c (tests committed in 1e58035 and amended content in a48438c)

**2. [Rule 1 - Bug] First test run leaked rows**
- **Found during:** Task 2
- **Issue:** failed runs left 21 `task` and 18 `pipeline_operation_log` rows of deleted documents (account cleanup does not remove them).
- **Fix:** removed the orphaned rows (documents no longer existing) and added the cleanup above.

### Other notes

- The RED commits contain the full test files; fixture fixes in the Task 2 test file were made while turning it green and are in the GREEN commit.
- The plan text listed `ParseLimits.max_pages` behaviour as an assumption; `count_pages` is used as it is after R-168 (hard ceiling 1,000,000, `FileTooLarge` caught like any `ParserError` and turned into the single full-range task).
- `_clean_ids` (document_service) and `_named_lock` (knowledgebase_service) are private helpers imported as the plan directs; promoting them to public names is a small follow-up.

## Known Stubs

None.

## Threat Flags

None. T-04-10-01..06 mitigations are applied and tested: permission judged on the token's subject, one NOT_FOUND for foreign ids, all-or-nothing confirmation with fresh counts, 100-id cap, lock plus row lock plus re-check, fixed messages with class-name-only logging.

## Self-Check: PASSED

Files exist; commits 9b27264, 72383b5, 1e58035, a48438c present.
