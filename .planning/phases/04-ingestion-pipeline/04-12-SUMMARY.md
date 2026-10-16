---
phase: 04-ingestion-pipeline
plan: 12
subsystem: ingestion
tags: [executor, valkey-streams, task-lock, watcher, rollup, reconciler, retry, shutdown]
requires:
  - phase: 04-07
    provides: TaskQueue, ValkeyStreamQueue, TaskLock
  - phase: 04-09
    provides: office/HTML parsers and router
  - phase: 04-10
    provides: task_service writers, claim_attempt, settle_totals, fail_documents
  - phase: 04-11
    provides: run_pipeline, TaskFailure, TaskControl, Limiters
provides:
  - rag/svr/executor_loop.py (Executor, Outcome, consumer_name)
  - rag/svr/heartbeat.py (TaskWatcher)
  - rag/svr/progress.py (rollup_once, reconcile_once, RollUpDaemon, RollupStats)
  - rag/svr/task_executor.py (python -m rag.svr.task_executor)
  - rag/svr/healthcheck.py (touch_alive, is_alive, ALIVE_FILE)
  - control.ShutdownRequested and TaskControl.shutdown; TaskLock.named / exists; open_client
  - task_service.watch_state, unfinished_tasks_for_reconcile, touch_task
  - test/helpers/executor_rig.py (in-process executors over the real stack)
affects: [04-13 and later ingestion API/UI plans, deployment (executor container, health probe)]
tech-stack:
  added: []
  patterns: [lock gate on every message, attempt counted under the lock, release lock before republish, row-locked state transition with run re-check, event-based waits]
key-files:
  created:
    - rag/svr/executor_loop.py
    - rag/svr/heartbeat.py
    - rag/svr/progress.py
    - rag/svr/task_executor.py
    - rag/svr/healthcheck.py
    - test/helpers/executor_rig.py
    - test/integration/test_rollup.py
    - test/integration/test_executor_loop.py
    - test/integration/test_executor_recovery.py
  modified:
    - rag/svr/control.py
    - rag/svr/task_lock.py
    - rag/svr/pipeline.py
    - api/db/services/task_service.py
    - test/helpers/ingest.py
    - test/integration/test_pipeline_failures.py
key-decisions:
  - "Pipeline runs on the executor's own thread inside task_limiter; the watcher thread is the only extra thread per task"
  - "The lock is released before a fresh message is published (retry and hand-on) so the next reader is not turned away by the lock gate"
  - "A lost lock leaves the message pending and refunds nothing; shutdown refunds the attempt; a retry backoff that is interrupted by shutdown hands on without a refund"
  - "worker_lost is recorded at step parse; failure sentences come only from PLAIN_MESSAGES via TaskFailure"
  - "The roll-up drops the [pages]/[skipped] machine lines from the user-visible merged message and reads the latest of each per task, so retried tasks do not double count"
  - "A user cancel (document run 2) keeps the chunks already indexed; only a replaced task, a deleted document or another run state removes the task's chunks"
  - "rollup_once takes an optional doc_ids filter (used by tests to stay isolated in the shared database)"
requirements-completed: []
duration: ~2h
completed: 2026-10-17
---

# Phase 4 Plan 12: Executor loop, roll-up daemon, reconciler and recovery

A runnable executor process now collects tasks from the Valkey priority streams, gates each message on the per-task lock, retries what can succeed, fails what cannot, honours cancel, hands its work on at shutdown or lock loss, and a lock-guarded roll-up daemon with a reconciler turns task rows into honest document state, proven in-process against the real MySQL, Valkey, Elasticsearch, MinIO and a loopback provider.

## Tasks

| Task | Commits | Result |
|------|---------|--------|
| 1 Watcher, shutdown control, named lock, roll-up, reconciler | RED e12b8b1, GREEN df1f582 | 19 integration tests pass |
| 2 Executor loop, entry process, health probe | RED b50110a, GREEN 9b30cd1 | 10 integration tests pass |
| 3 Lock loss, reclaim, shutdown, outage recovery | ce45ed9 | 5 integration tests pass |

## Verification

- `uv run python -m pytest -m integration test/integration/test_rollup.py test/integration/test_executor_loop.py test/integration/test_executor_recovery.py`: 34 passed (the earlier pipeline suites, `test_indexing.py` and `test_pipeline_failures.py`, also pass: 23 and 39 passed in the runs after each change).
- `uv run python -m pytest test/unit_test`: 1927 passed, 3 skipped.
- `uv run python scripts/ci/run_all.py`: 7/7 gates.
- `wc -l rag/svr/executor_loop.py`: 229. No `sleep(` in the three integration files and no `time.sleep` under `rag/svr`.
- `python -m rag.svr.task_executor` started against the stack, logged to stdout only, and exited 0 on SIGTERM. `init_root_logger` is called with log directory `None`.
- The Valkey outage test stops and restarts the `redis` compose service; the stack was healthy again afterwards.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] A user cancel removed the chunks already indexed**
- **Found during:** Task 2 (cancel test: chunk count fell to 0 after cancel)
- **Issue:** `_current_switch` in the pipeline treated `document.run != "1"` as a stale task and deleted its chunks. That raced with the watcher's cancel event and contradicted D-06 and `cancel_parse` ("chunks and totals are kept"). The 04-11 test asserted the old behaviour.
- **Fix:** run `"2"` with a current task row now stops with `TaskCancelled` and keeps the chunks; a gone task, a deleted document and any other run state still remove the task's chunks. The 04-11 test is parametrized: `run 2` keeps, `run 0` removes.
- **Files modified:** rag/svr/pipeline.py, test/integration/test_pipeline_failures.py
- **Commit:** 9b30cd1

### Plan variations

- `rollup_once(settings, *, doc_store=None, doc_ids=None)`: the plan's `queue` argument was dropped (the roll-up never uses it); `doc_ids` was added for test isolation.
- `unfinished_tasks_for_reconcile(older_than_ms, limit)`: no `cap` argument. Tasks that used every attempt are included on purpose so their next delivery fails them as `worker_lost`.
- `pipeline.py` did not write the `[pages]` and `[skipped]` lines yet; added at the end of `run_pipeline`.
- `test/helpers/executor_rig.py` is a new helper file (not in the plan's file list) holding the in-process executor rig.
- Task 3 tests passed on first run: the counters and branches they need (`last_error`, `outcomes`, `LOST`, `SHUTDOWN`, `interrupt_all`) were built with the loop in Task 2, so there was no separate RED commit for Task 3.

## Known Stubs

None.

## Threat Flags

None. T-04-12-01..07 mitigations are applied and tested: message content never trusted (digest and gone-task tests), lock gate and displaced-owner tests, attempts counted before work (`worker_lost`), failure lines from typed codes only (log and progress scans in the damaged-file test), outage handling that never exits, one log row per run with structured error, and a row-locked `run == "1"` re-check in the transition (cancel-race test).

## Notes for later plans

- `elastic_transport` and other HTTP client loggers should be at WARNING or above in deployment logging (carried over from 04-11).
- `kg_limiter` is still unused.
- The container health probe is `python -m rag.svr.healthcheck` (exit 0 while the alive file is younger than `ingest.worker_heartbeat_timeout`).

## Self-Check: PASSED

Files exist (executor_loop, heartbeat, progress, task_executor, healthcheck, executor_rig, three integration suites); commits e12b8b1, df1f582, b50110a, 9b30cd1, ce45ed9 present.
