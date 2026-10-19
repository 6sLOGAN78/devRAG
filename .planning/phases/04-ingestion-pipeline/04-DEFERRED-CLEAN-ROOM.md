---
phase: 04-ingestion-pipeline
item: clean-room exit gate (plan 04-35 task 3)
status: deferred
deferred_on: 2026-10-19
deferred_by: user ("stop that check, make a doc so we can check later, and finish phase 4")
blocker: B-36
---

# Phase 4 deferred check: three clean-room runs

The Phase 4 exit gate is three consecutive passes of `scripts/clean_room.sh --runs 3`. Each run stops the stack, rebuilds it from scratch and runs every test tier. The gate has **not** passed. The user decided on 2026-10-19 to close Phase 4 now and run the gate later. This file says what was done, what is still unproven, and how to finish it.

## How to run it later

From the repository root, with the stack's own containers only (no `devRag_@` checkout running under project `devrag-stack`):

```bash
PREFLIGHT_ALLOW_LOW_MAP_COUNT=1 LIVE_BASE_URL=http://127.0.0.1:8088 scripts/clean_room.sh --runs 3
```

- `PREFLIGHT_ALLOW_LOW_MAP_COUNT=1` is needed while the host has `vm.max_map_count` 65530. Elasticsearch runs at that value on this host. The permanent fix needs the user's own `sudo sysctl -w vm.max_map_count=262144`. After that the flag can be dropped.
- One attempt takes roughly 30 to 40 minutes per run. The live tier calls the real OpenRouter API and needs the key the Phase 3 live tests use.
- Pass condition: the log ends with `clean-room: 3 run(s) passed` and exit 0. Append that line to `04-35-GATE-LOG.md`.

## When it passes

1. Append the result to `04-35-GATE-LOG.md`.
2. In `04-VALIDATION.md`, set `nyquist_compliant: true`, `wave_0_complete: true` and `status: approved`, then remove the "NOT approved" note.
3. Close B-36 in `.planning/BLOCKERS.md` and set this file's `status: done`.

## Attempts so far (2026-10-19)

| # | Got as far as | Result | Cause | Fix |
|---|---|---|---|---|
| 1 | `project-guard` | refused before touching anything | `devrag-stack-mailpit-1` came from an old checkout (`devRag_@`) | user approved `docker rm -f devrag-stack-mailpit-1` (no volume) |
| 2 | run 1, integration | 2 of 642 failed | two tests out of date after Phase 4 decisions: dataset test set unbuilt `book` method (D-27); executor memory test expected 768m, now 384m (R-188) | `d65664e` |
| 3 | run 1, integration | 1 of 642 failed | **real bug:** the roll-up finished a document and closed its log row in two separate commits; a reader could see Finished with log `running`, and a crash between them left the log `running` for ever | `2925739`, with a regression test |
| 4 | run 1, e2e | 1 of 662 failed | e2e twin of the out-of-date dataset test (`book`) | `4d651f6` |
| 5 | run 1, live-model | 16 setup errors | OpenRouter unreachable from the container (`provider_unreachable`, `ERROR_CONNECTION`); minutes later it answered and all 17 live tests passed | none needed (network) |
| 6 | run 1, early | stopped by the orchestrator | user asked to defer the gate | — |

Run 1 of attempt 5 passed every tier before the live one. In order: project guard, stop, preflight, rebuild, wait, unit 2055, integration 643, e2e 662, e2e-serial 13.

## Every tier checked once against the running stack

Run outside the clean room on 2026-10-19, against a stack rebuilt from the current tree:

| Tier | Result |
|---|---|
| Python unit | 2055 passed, 4 skipped |
| Python integration | 643 passed (inside attempt 5) |
| Python e2e, not serial | 662 passed |
| Python e2e, serial | 13 passed |
| Python live_model (real OpenRouter) | 17 passed. One live test was hardened first: the nearest-chunk helper asked kNN for k=3, which gives only 6 HNSW candidates; now k=32 (`ed9e383`) |
| Go race | passed |
| Go integration + e2e | passed (with `SERVICE_CONF`, `E2E_BASE_URL`, `MYSQL_ROOT_PASSWORD` set as `clean_room.sh` sets them) |
| Go manual, Go cgo | passed |
| Web unit (vitest) | 82 files, 1703 tests passed |
| Web live (vitest) | 14 files, 57 tests passed on rerun. One earlier run failed the Phase 3 Models page test 4 times right after heavy live provider use; it passed alone and in the full rerun (see "Known flaky" below) |
| CI gates (`scripts/ci/run_all.py`) | 7 of 7 |

## What is still unproven

- **Three consecutive runs from a wiped stack.** No attempt has passed even one full run. Every tier has passed on its own, but not all in one run from a clean stack.
- **The `memory` step** of the gate (`scripts/record_memory.py --record`). The executor limit itself was measured in plan 04-35: a 201 MiB peak against the 384m limit (R-188).
- **Repeatability of the live tier.** It depends on OpenRouter being reachable.

## Known flaky or environment-dependent items

- **Live tier and network:** the live tier fails outright, not skipped (D-04), when OpenRouter cannot be reached. A failure there with `provider_unreachable` in the app log is the network, not the code.
- **Models page live test:** `web/src/pages/user-setting/model/models.live.test.ts` failed once right after the Python live tier had used the provider heavily, and passed twice afterwards. It is likely slow provider answers. Watch it in the gate.

## Requirements affected

The gate is the last proof for TEST-11, E2E-05 and E2E-06. Each of these is covered by passing tests in its own tier (see the table above), so they are recorded as complete. The three-run repeat is what stays open, under this file and B-36.
