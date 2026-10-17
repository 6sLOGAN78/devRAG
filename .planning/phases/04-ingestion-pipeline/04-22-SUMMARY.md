---
phase: 04-ingestion-pipeline
plan: 22
subsystem: testing
tags: [e2e, executor, crash-recovery, poison, cancel, partial-failure, reparse, scaling, graceful-stop]
requires:
  - phase: 04-12
    provides: executor loop, lock, reclaim, shutdown hand-on
  - phase: 04-13
    provides: executor container, docker-compose.executor-test.yml timing override
  - phase: 04-21
    provides: format and PDF journeys, shared ingest helpers
provides:
  - test/helpers/executor_control.py (compose control of the executor service, owner lookup, kill and stop)
  - test/testcases/test_ingestion_failure.py (7 journeys)
  - test/testcases/test_ingestion_scaling.py (2 journeys)
  - executor re-settles totals when a task stops on a cancel
affects: [04-33 live tier, clean-room gate]
tech-stack:
  added: []
  patterns: [module fixture recreates the executor with the fast-timing override and restores the default in finally, containers found by compose labels, owner of a task from XPENDING mapped by hostname prefix, provider knobs (delay_ms, embed_mode) instead of production hooks]
key-files:
  created:
    - test/helpers/executor_control.py
    - test/testcases/test_ingestion_failure.py
    - test/testcases/test_ingestion_scaling.py
  modified:
    - rag/svr/executor_loop.py
    - test/integration/test_executor_loop.py
    - test/testcases/test_parse_flow.py
    - test/testcases/test_delete_chunks_flow.py
key-decisions:
  - "R-179: the executor settles totals again when a task stops on a cancel; test containers are located by label, not by name suffix"
requirements-completed: []
duration: about 75 min
completed: 2026-10-17
---

# Phase 4 Plan 22: Crash, poison, cancel, partial failure, re-parse and scaling Summary

Killed workers, poison files, cancels, a refusing provider, re-parses, a second executor and a graceful stop are proven on the real executor containers, and the work found and fixed one product defect (totals stale after a cancel).

## What was proven

- Kill: two fast executors, 40-chunk TXT, embeddings delayed 300 ms. The container that owns the pending task is killed part-way. The task is reclaimed and the document finishes: exactly 40 ids `_0.._39`, no duplicates, the task manifest equals the index, `retry_count` is 2 or 3, no pending stream entry. Measured kill to `run 3`: 23.6 s and 24.6 s in two runs.
- Poison: truncated DOCX fails with `file_damaged` after exactly 3 attempts (`progress -1`), plain sentence in the log detail, `retried true`, zero embedding requests at the provider, no `Traceback`, `/ragflow`, `/tmp`, loopback host or key shape in the list row, log detail, task status or the executor logs.
- Cancel: the list row reads `run 2` within 5 s of the request; chunks already indexed stay (0 < kept < 40), the count stays stable for three polls, `chunk_count` equals the index, the log entry closes as `cancelled`, Parse again needs no dialog and finishes with 40 exact ids.
- Partial failure: the provider is flipped to refuse after chunks were indexed; the document ends `run 4` with `provider_refused`, `retried false`; the earlier chunks are still in the index, counted and `available_int 1`; Parse again replaces them and ends with 40.
- Edited-chunk guard: after such a failure an edited chunk makes Parse again 409 `confirm_required` with `edited_count 1`; the confirmed re-parse ends with 40 chunks and the edit gone.
- Re-parse identity: the id set is identical after a confirmed re-parse, after a cancelled run and after a failed run.
- Delete during a parse: the index count reaches 0 and stays 0 for three polls; no traceback in the executor logs.
- Scaling: `--scale task-executor=2` with the override only; both register as group consumers; six documents finish with `retry_count 1` each, no duplicate ids, no pending entries. A graceful `docker stop` of the owner exits 0, the other executor finishes the document with exact ids, `retry_count` stays 1 (attempt refunded).
- After each module exactly one healthy default executor remains (fixture asserts it, and that the override environment is gone).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Totals stale after a cancel with a batch in flight**
- **Found during:** Task 2 (first full run; the cancel test passed once by luck, then failed with the document total never equalling the index)
- **Issue:** `cancel_parse` settles `chunk_num` and the dataset counters when the request lands. A batch already being embedded is still written afterwards (D-06), so the document total stayed below the index count and nothing re-counted it.
- **Fix:** the executor calls `settle_totals` when a task stops on `TaskCancelled`, before acknowledging. A failed settle is logged and does not block the acknowledgement.
- **Regression test:** `test_cancel_keeps_the_document_cancelled_and_the_task_stops_within_three_seconds` now also waits for `chunk_num` to equal the settled index count. It failed before the fix (8 != 16) and passes after.
- **Files modified:** rag/svr/executor_loop.py, test/integration/test_executor_loop.py
- **Commit:** 3d8f4d1

**2. [Rule 3 - Blocking] Executor container name changes when the service is recreated**
- **Found during:** after Task 1 (recreated containers are named `task-executor-2`, `-4`, `-5`)
- **Issue:** `test_parse_flow.py` and `test_delete_chunks_flow.py` read logs from `devrag-stack-task-executor-1`, which no longer exists after any recreate.
- **Fix:** both use `executor_control.container_ids()` (compose labels) and `logs_since`.
- **Commit:** 3d8f4d1

### Plan variations

- Embedding delay is 300 ms (plan: 150 ms) so the kill and cancel always land mid-task with batch size 2. Same knob, no production hook.
- Test names carry the selector words (`poison`, `delete`) so the plan's `-k` expressions select them.
- `test/helpers/ingest.py` needed no change.
- Stale consumers of removed containers stay listed in Valkey, so the scaling test counts only consumers that map to a running container.

## Verification

- `uv run python -m pytest -m "e2e and serial" test/testcases/test_ingestion_failure.py test/testcases/test_ingestion_scaling.py -q`: 9 passed in 131 s (after the fix and a stack rebuild).
- `uv run python -m pytest test/integration/test_executor_loop.py test/integration/test_executor_recovery.py -q`: 15 passed.
- `uv run python -m pytest -m e2e test/testcases/test_parse_flow.py test/testcases/test_delete_chunks_flow.py -q`: 19 passed.
- `uv run python scripts/ci/run_all.py`: 7/7 gates. No `sleep(` in the new files. ruff check clean.
- Stack rebuilt with the fix (`up -d --build`, cpu, elasticsearch and mail profiles); at the end one healthy default task-executor.

## Known Stubs

None.

## Threat Flags

None. T-04-22-01 (restore in `finally`, one healthy container asserted), T-04-22-02 (containers found only by the project label) and T-04-22-03 (logs scanned, never printed) are applied.

## Self-Check: PASSED

Files exist (executor_control.py, test_ingestion_failure.py, test_ingestion_scaling.py); commits cb5c9cc, d76faa0, 6abbba4, 3d8f4d1 present.
