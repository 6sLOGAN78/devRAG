---
phase: 04-ingestion-pipeline
plan: 07
subsystem: ingestion
tags: [valkey, streams, queue, lock, xautoclaim]
requires:
  - phase: 04-03
    provides: IngestSettings (queue_prefix, consumer_group, reclaim and heartbeat values)
  - phase: 04-06
    provides: parser and chunker contracts
provides:
  - TaskQueue ABC, QueueMessage, QueueUnavailable, MessageMalformed
  - ValkeyStreamQueue (priority streams, consumer group, XAUTOCLAIM takeover, XACK+XDEL, heartbeat)
  - get_queue / reset_queue_cache
  - TaskLock, LockLost, LockNotAcquired, lock_key
affects: [04-10, 04-12, worker executor]
tech-stack:
  added: []
  patterns: [fixed-message typed errors, library lock script for compare-and-delete, per-test queue prefix]
key-files:
  created:
    - rag/queue/{__init__,queue_base,valkey_streams,factory}.py
    - rag/svr/{__init__,task_lock}.py
    - test/unit_test/test_queue_message.py
    - test/integration/{test_queue,test_task_lock_reclaim}.py
  modified:
    - test/unit_test/test_layering.py
key-decisions:
  - "Message body is one stream field `message` holding JSON {task_id, digest}; extra keys or a non-32-hex task_id are malformed"
  - "read() polls priority 1 without blocking first, then blocks on both streams, so priority 1 always drains first"
  - "Malformed entries are XACKed and XDELed with a log line carrying only stream and id"
  - "TaskLock takes a `prefix` keyword (default `te`) so the key is {prefix}.lock.task_{id} and tests stay isolated"
  - "Delivery count after a claim comes from XPENDING (times_delivered); first reads report 1"
requirements-completed: []
duration: ~25min
completed: 2026-10-17
---

# Phase 4 Plan 07: Task Queue and Task Lock Summary

Valkey Streams task queue (priority-first reads, one consumer group, XAUTOCLAIM takeover without justid, XACK+XDEL) and an owner-token task lock on valkey's own lock script, proven against the stack's real Valkey.

## Tasks

| Task | Commit | Result |
|------|--------|--------|
| 1 Queue interface, codec, Valkey Streams | 3a9d833 | 8 integration + 19 unit tests (with layering) pass |
| 2 Owner-token task lock and reclaim | c353fce | 6 integration tests pass, including live-owner and expired-owner reclaim |

## Verification

- `uv run python -m pytest -m integration test/integration/test_queue.py test/integration/test_task_lock_reclaim.py` : 14 passed
- Unit: queue message and layering tests pass; `scripts/ci/run_all.py`: 7/7 gates
- Teardown asserts no key with the test prefix remains; no `sleep(` in the tests; no `justid` or `nats` under `rag/queue`
- Outage test: `QueueUnavailable` text contains neither host, port nor password

## Deviations from Plan

None. The acceptance grep for `justid` initially matched a docstring; the wording was changed in the same task commit.

## Notes

- The tests read `queue._client` for XPENDING/XLEN assertions; it is a test-only use of a private attribute.
- Renewal period, TTL ownership and the lock gate on received messages are for plan 04-12.

## Self-Check: PASSED

Files and commits 3a9d833, c353fce exist.
