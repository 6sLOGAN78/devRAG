---
phase: 03-models-knowledge-bases-and-upload
plan: 29
subsystem: phase-exit-gate
tags: [traceability, clean-room, live-model, validation, phase-exit]

requires:
  - phase: 03-models-knowledge-bases-and-upload
    provides: "plans 03-01 to 03-28, 03-30 and 03-31 (code, tests, records)"
provides:
  - "test/unit_test/test_phase3_traceability.py: requirement, decision, registry-row and summary traceability"
  - "three consecutive green clean-room runs (scripts/clean_room.sh --runs 3, web port 8088, provider key present, live-model step included)"
  - "03-VALIDATION.md signed off (status approved, wave_0_complete true)"
  - "four gate-found defects fixed at their source (see Deviations)"
affects: [Phase 3 verification, Phase 4 planning]

key-files:
  created:
    - test/unit_test/test_phase3_traceability.py
    - .planning/phases/03-models-knowledge-bases-and-upload/03-29-GATE-LOG.md
  modified:
    - test/testcases/test_live_models.py
    - internal/e2e/matrix_fixtures_test.go
    - test/testcases/test_auth_flow.py
    - test/unit_test/test_secretbox.py
    - .planning/DECISIONS.md
    - .planning/phases/03-models-knowledge-bases-and-upload/03-VALIDATION.md

key-decisions:
  - "R-153: the Go cross-tenant matrix covers the scope-tenant rows with owner go; the 17 Python-owned Phase 3 rows are covered, with the same registry-wide guard, by the Python matrix (a superset)."
  - "The gate ran with PREFLIGHT_ALLOW_LOW_MAP_COUNT=1 only (B-02: vm.max_map_count is 65530 after the host restart, no sudo); no other threshold was lowered."

requirements-completed: [TEST-08, E2E-03, E2E-04, UI-10, UI-11, UI-12, UI-37, SEC-02, SEC-03, SEC-06]

duration: about 5 hours elapsed, mostly gate wall time (4 gate attempts)
completed: 2026-10-10
---

# Phase 3 Plan 29: Traceability test and phase exit gate Summary

**The Phase 3 slice passed `scripts/clean_room.sh --runs 3` three times in one invocation against the real stack and the real OpenRouter account (every step PASS each run, `live-model` included), after the gate had found and I had fixed one scoping defect in the Go matrix, one latent random-failure test pattern and one stale unit test that needed the stack; 03-VALIDATION.md is approved.**

## Commits

| Item | Commit | Description |
|------|--------|-------------|
| Pre-fix | `94b31d8` | `fix(03-27)`: the live file's missing-key failure is raised before the stack wait |
| Task 1 | `20b4a0d` | `test(03-29)`: Phase 3 traceability test |
| Gate fix 1 | `73c2350` | `fix(03-19)`: Go cross-tenant matrix scoped to the rows Go owns (R-153) |
| Gate fix 2 | `978138b` | `fix(02-14)`: tamper the first signature character, not the last |
| Gate fix 3 | `201c254` | `fix(03-02)`: same latent pattern in the secretbox unit test |
| Task 2 | this plan's final `docs(03-29)` commit | validation sign-off, summary, state |

## Pre-fix (deferred item 5)

`test_without_the_key_the_live_tier_fails_and_does_not_skip` waited 120 s for the stack and failed whenever it was down. Cause: the session fixture `ingress` (which waits for the stack) was instantiated before the module fixture `live_env` (which raises the missing-key failure). Fix: a module-scoped `ingress` override in `test/testcases/test_live_models.py` that lists `live_env` first and returns the session `ingress`. The assertions, the marker and the unit tier placement are unchanged.

Proof with the stack down (host had just rebooted, `devrag-stack-app-1` crash-looping, no listener on 8088): before the fix the guard test failed after 121 s; after it passes in 1.0 s; `uv run python run_tests.py -m unit` = 1811 passed, 1 skipped, 0 failed, 43.7 s wall.

## Task 1: traceability test

`test/unit_test/test_phase3_traceability.py` (`pytestmark = pytest.mark.unit`, 6 tests): the phase requirement list is expanded from ranges in the test and each ID must appear in some `03-NN-PLAN.md` `requirements:` list; each of D-01..D-29 must be cited in some plan's `must_haves` block; every `/api/v1/providers|models|datasets|documents` registry row is `implemented: true`; and, only with `PHASE3_GATE=1`, every plan except 03-29 has a SUMMARY. It passed first time (no gap to repair). `gen_routes.py --check` and `scripts/ci/run_all.py` (7/7 gates) pass.

## Pre-gate checks (all passed)

- `PREFLIGHT_REQUIRE_LIVE_KEY=1 scripts/preflight.sh` with `PREFLIGHT_ALLOW_LOW_MAP_COUNT=1`: `OK openrouter key: present`, RAM 7231 MB available (need 4096), disk 17.0 GB, ports free, project guard OK; web port in docker/.env is 8088.
- `scripts/ci/run_all.py` 7/7, `gen_routes.py --check`, `go vet ./...`, `go test ./internal/common/... -count=1`.
- `cd web`: `npm run typecheck`, `npm run test -- --run` (56 files, 1135 tests, 26.8 s), `npm run build`.
- `PHASE3_GATE=1 pytest test/unit_test/test_phase3_traceability.py`: 6 passed.

## The gate: four attempts, three clean runs in the last one

| Attempt | Result | Cause | Action |
|---------|--------|-------|--------|
| 1 | run 1 FAIL at `go-tiers` (after PASS unit, integration, e2e, e2e-serial, live-model, go-race) | Go cross-tenant matrix test read all 25 scope-tenant rows; the 17 Python-owned Phase 3 rows had no Go fixtures | fix, R-153 |
| 2 | run 1 FAIL at `live-model` (6 setup errors, `PUT /api/v1/providers` -> 504) | App log: `embedding call failed provider=OpenRouter model=baai/bge-m3 code=ERROR_TIMEOUT` at the 30 s embedding timeout, product answered `provider_timeout`. Two timed direct calls right after returned 200 in 1.9 s each. Transient provider latency, product behaved as designed | no code change, nothing loosened, gate restarted |
| 3 | run 1 FAIL at `e2e` (`test_tampered_and_foreign_tokens_are_401_on_python`, got 200) | Test defect: it flipped the last base64 character of the 27-character HMAC signature, which carries 2 padding bits that itsdangerous ignores, so the token stayed valid 7.2 % of the time (measured on 2000 tokens) | fix in test_auth_flow.py and the same latent pattern in test_secretbox.py |
| 4 | **3 run(s) passed** | | |

Restarts of the whole gate: 3 (after each of attempts 1, 2 and 3), always from run 1. No host restart happened during the gate attempts (host up since 04:43 local).

### Final attempt 4: per-step results (identical in runs 1, 2 and 3)

```
PASS project-guard   PASS stop   PASS preflight   PASS up   PASS wait_stack
PASS unit   PASS integration   PASS e2e   PASS e2e-serial   PASS live-model
PASS go-race   PASS go-tiers   PASS go-manual   PASS go-cgo
PASS vitest-unit   PASS vitest-live   PASS memory
clean-room: 3 run(s) passed          (PASS live-model appears 3 times)
```

| Measure | Run 1 | Run 2 | Run 3 |
|---------|-------|-------|-------|
| time-to-healthy | 37 s | 43 s | 45 s |
| unit tier (`-m unit`) | 1816 passed, 2 skipped, 40.0 s | 1816 passed, 2 skipped, 39.2 s | 1816 passed, 2 skipped, 46.3 s |
| integration | 416 passed, 242.9 s | 416 passed, 259.9 s | 416 passed, 252.2 s |
| e2e (not serial) | 459 passed, 202.1 s | 459 passed, 206.0 s | 459 passed, 201.7 s |
| e2e-serial | 4 passed, 58.4 s | 4 passed, 59.3 s | 4 passed, 60.4 s |
| live-model | 6 passed, 29.0 s | 6 passed, 28.6 s | 6 passed, 27.0 s |
| whole run | 746 s | 782 s | 762 s |

Unit-tier skips (2): the `PHASE3_GATE`-guarded summary check (by plan design; run separately with `PHASE3_GATE=1`, passed) and one Phase 1 numpy test (B-13, pre-existing).

Memory record lines (run 3, `--record`, after the full suites): app 266.9 MiB (limit 768), es01 1532.9 (2048), mailpit 27.9 (64), minio 122.2 (256), mysql 287.5 (640), redis 4.6 (160); total 2242.0 MiB of the 3891 MiB budget. Host free disk after the runs: 16 to 17 GB. `scripts/record_memory.py --record` rewrote the "Dev memory budget" table in `.planning/DECISIONS.md` with these figures.

Live provider calls: the Python live tier is capped at 6 chat-class and 3 embedding calls per run plus about 4 for the web Models journey; across the four attempts, one manual `npm run test:live` pre-run and two timed diagnostic embedding calls the total was roughly 55 real OpenRouter calls. No key value was printed, logged or written: `grep OPENROUTER` over the gate log finds nothing, and `docker/.env` is unchanged and git-ignored.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Go matrix read Python-owned rows**
- **Found during:** gate attempt 1, step `go-tiers`
- **Issue:** `internal/e2e` `loadTenantRows` took every implemented scope-tenant row; since Phase 3 added 17 Python-owned rows with no Go fixture, `TestCrossTenantRegistryCoverage`, `TestCrossTenantGuardFailsRowsWithoutFixtures` and `TestCrossTenantMatrix` failed. No Phase 3 plan had run the Go e2e tier.
- **Fix:** rows are filtered to `owner: go`; the Python matrix keeps covering all 25 rows with its own coverage guard. Recorded as R-153. The Go assertions on the eight Go-owned rows are unchanged. The whole go-tiers command, go-manual, go-cgo and `test:live` were then run by hand against the live stack before restarting the gate: all ok.
- **Files modified:** `internal/e2e/matrix_fixtures_test.go`, `.planning/DECISIONS.md`
- **Commit:** `73c2350` (owning plan 03-19)

**2. [Rule 1 - Bug] Random failure of the tampered-token test**
- **Found during:** gate attempt 3, step `e2e`
- **Issue and fix:** see the table above; the test now flips the first signature character (0 of 3000 accepted).
- **Files modified:** `test/testcases/test_auth_flow.py`
- **Commit:** `978138b`

**3. [Rule 1 - Bug] Same pattern in the secretbox unit test**
- **Found during:** investigating deviation 2
- **Issue:** `test_tampered_envelope_fails` flipped the last base64 character; a flip left the envelope readable about 1 % of the time, a latent random failure of the unit tier. Fixed by flipping the second-to-last, always significant, character (0 of 3000 accepted).
- **Files modified:** `test/unit_test/test_secretbox.py`
- **Commit:** `201c254`

**4. [Rule 1 - Bug] Unit-tier test needed the stack (deferred item 5)**
- **Commit:** `94b31d8`, described above.

### Not changed

- B-32 (`forgot-password.test.tsx` 5 s timeout under load) did not occur in any vitest-unit execution of this plan (the pre-gate run and the four gate executions); no worker cap or timeout change was made.
- The attempt 2 provider timeout was not "fixed": it is an external latency event, and neither a timeout nor a retry count was raised.

## Auth gates

None. The provider key was present; OpenRouter never answered 401 or 402.

## Known Stubs

None found in the files this plan touched.

## Threat Flags

None. The only new file of product relevance is a test; the gate log and this summary carry no secrets.

## Self-Check

- `test/unit_test/test_phase3_traceability.py`, `03-29-GATE-LOG.md`, `03-VALIDATION.md` exist; commits `94b31d8` and `20b4a0d` exist; the gate log ends with `clean-room: 3 run(s) passed`.

## Self-Check: PASSED
