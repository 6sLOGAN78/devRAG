---
phase: 04-ingestion-pipeline
plan: 13
subsystem: deployment
tags: [docker-compose, task-executor, tini, setpriv, valkey, volatile-lru, healthcheck]
requires:
  - phase: 04-03
    provides: settings and env catalog
  - phase: 04-12
    provides: python -m rag.svr.task_executor and python -m rag.svr.healthcheck
provides:
  - task-executor compose service (profile cpu), same image as app, scalable with --scale
  - docker/entrypoint_task_executor.sh and docker/healthcheck_task_executor.sh
  - docker/docker-compose.executor-test.yml (crash-test timings, executor only)
  - Valkey maxmemory-policy volatile-lru
  - test/integration/test_executor_container.py, test/unit_test/test_compose_files.py
affects: [later ingestion API/UI plans, 04-35 memory measurement]
tech-stack:
  added: []
  patterns: [exec after setpriv so tini signals Python, dev-only settings only in the dev override, nameless scalable service]
key-files:
  created:
    - docker/entrypoint_task_executor.sh
    - docker/healthcheck_task_executor.sh
    - docker/docker-compose.executor-test.yml
    - test/unit_test/test_compose_files.py
    - test/integration/test_executor_container.py
  modified:
    - Dockerfile
    - docker/docker-compose.yml
    - docker/docker-compose.dev.yml
    - docker/docker-compose-base.yml
    - rag/svr/task_executor.py
    - test/unit_test/test_container_scripts.py
key-decisions:
  - "Scaled copies share one image and need no names: no container_name, no published port, consumer name is te_<host>_<pid>_<rand>"
  - "Valkey uses volatile-lru so TTL-less stream entries are never evicted (R-157)"
  - "Executor process keeps elastic_transport, urllib3, httpx and httpcore at WARNING"
requirements-completed: []
duration: ~1h30m
completed: 2026-10-17
---

# Phase 4 Plan 13: Executor container, overrides and Valkey policy

The parsing worker now runs as its own `task-executor` compose service (same image, tini then setpriv then `exec python -m rag.svr.task_executor`), healthy only while its alive file is fresh, scalable to two with one flag, stopping with exit 0 on SIGTERM, on a Valkey that no longer evicts stream entries.

## Tasks

| Task | Commits | Result |
|------|---------|--------|
| 1 Scripts, service, overrides, Valkey policy, static tests | fb22f4e (tests written first and seen failing: 10 failed before the files existed) | 86 static tests pass |
| 2 Container tests, one rebuild, live proof | 75da036 | 7 live tests pass |

## Red run (Task 2, D-22)

`test_executor_container.py` run against the stack before the rebuild: 7 failed (no `task-executor` container in the old image, policy still `allkeys-lru`).

## Verification

- `uv run python -m pytest -m integration test/integration/test_executor_container.py`: 7 passed (healthy, logs free of Traceback and secrets, consumer `te_*` registered in `te.0.common` / `ragflow_consumer_group`, policy `volatile-lru`, memory 768 MiB and unprivileged process, scale to two with distinct consumers, graceful stop exit 0 then restored).
- `uv run python -m pytest test/unit_test`: 1938 passed, 3 skipped. `scripts/ci/run_all.py`: 7/7 gates.
- `scripts/record_memory.py`: exit 0, task-executor 64.2 MiB of 768; total 1860 MiB of 3891.
- After the run exactly one task-executor container remains; `scripts/wait_stack.sh` reports all services healthy. `scripts/clean_room.sh` and `test_clean_room_guard.py` unchanged. No `sleep(` in the new integration file.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `make up` preflight cannot pass on a running stack**
- **Found during:** Task 2
- **Issue:** preflight fails because the project's own containers hold the ports (and `vm.max_map_count` is 65530 although ES already runs healthy).
- **Fix:** ran the exact `make up` compose command (`up -d --build` with cpu, elasticsearch, mail profiles) and `scripts/wait_stack.sh` directly. Same effect, preflight skipped.

**2. [Rule 1 - Bug] Test defects found on the first live run**
- The Valkey client used db 0; the app uses `REDIS_DB` default 1. The unprivileged-process check used `docker exec id -u`, which runs as root; it now reads `docker top` for the executor process user. Test bugs only, no assertion loosened.

**3. [Rule 2 - Missing] Transport loggers**
- Added `QUIET_LOGGERS` (elastic_transport, urllib3, httpx, httpcore at WARNING) in `rag/svr/task_executor.py` as the orchestrator requested (carry-over from 04-11/04-12).

### Plan variations

- `scripts/record_memory.py` needed no change: it discovers services from docker, there is no service table.
- `test_compose_infra.py` did not assert the old policy, so it was not edited.
- The executor-test override is pinned statically only; no live test applies it here (later crash tests do).

## Known Stubs

None.

## Threat Flags

None. T-04-13-01..05 mitigations applied and tested (privilege drop, log scan, volatile-lru, dev settings absent from the production file, 768m limit).

## Notes for later plans

- Docker stack state at end: devrag-stack up and healthy (app, task-executor x1, mysql, redis, minio, es01, mailpit; init exited 0). Redis was recreated by the policy change, so its keys (db 1) were reset; the executor recreated its groups on start.
- The `app` and `mailpit` containers had been created from a different working directory (`devRag_@/docker`); `up` recreated `app` from this tree.

## Self-Check: PASSED

Files exist (scripts, three compose files, two test files); commits fb22f4e and 75da036 present.
