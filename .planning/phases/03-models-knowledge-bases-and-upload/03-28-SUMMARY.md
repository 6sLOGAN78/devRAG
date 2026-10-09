---
phase: 03-models-knowledge-bases-and-upload
plan: 28
subsystem: records
tags: [decisions, blockers, litellm-pin, claude-md, b-09, consistency-test]

requires:
  - phase: 03-models-knowledge-bases-and-upload
    provides: "the SUMMARY.md files of plans 03-01 to 03-27, 03-30 and 03-31 and deferred-items.md (facts the rows are written from)"
provides:
  - "DECISIONS.md rows R-136 to R-152 (17 rows) for every Phase 3 choice that docs/ does not settle"
  - "CLAUDE.md stack notes aligned with the installed packages (litellm 1.103.2, openai range, two unused libraries)"
  - "B-09 closed; B-31, B-32 and B-33 opened for the open risks and host notes of the phase"
  - "test/unit_test/test_phase3_records.py (records, pin and package checks)"
affects: [03-29, Phase 4 planning, Phase 3 verification]

key-files:
  created:
    - test/unit_test/test_phase3_records.py
  modified:
    - .planning/DECISIONS.md
    - .planning/BLOCKERS.md
    - CLAUDE.md
    - .planning/phases/03-models-knowledge-bases-and-upload/deferred-items.md

key-decisions:
  - "The plan listed R-136 to R-147; five further rows (R-148 to R-152) hold decisions the summaries recorded that no planned row fitted: log masking limit, usage counters and log fields, route generator tightening, locale key prefixes, dialog stacking. The test pins all 17."
  - "Every row is 'accepted (auto, not user-reviewed)'; the user-confirmed set was not touched and CONTEXT D-01 to D-23 are cited as sources, not turned into rows."
  - "R-19, R-21 and R-50 got a one-sentence cross-reference to the Phase 3 outcome (R-21 moved from open to accepted because Phase 3 settled it as R-144)."

requirements-completed: [LLM-02, LLM-16, SEC-03, IDX-04, STOR-10, DOC-03, KB-01, TEN-13, UI-12]

duration: resumed after interruption
completed: 2026-10-10
---

# Phase 3 Plan 28: Decision records, litellm pin and B-09 closure Summary

**Seventeen decision rows (R-136 to R-152) record what Phase 3 built beyond docs/, CLAUDE.md now pins litellm 1.103.2 in both places and agrees with pyproject.toml and uv.lock, B-09 is closed on the evidence of the live OpenRouter tier, and a unit test fails if any of these drift.**

## Interrupted run and resume

The first executor committed Task 1 (`ebcb21e`, failing records test, 7 of 12 failing) and left Task 2 uncommitted in the working tree: about 17 rows in DECISIONS.md, the CLAUDE.md edits and the BLOCKERS.md changes. The resume read that diff against the plan and against every Phase 3 SUMMARY and `deferred-items.md`, kept it, checked each row's facts, corrected one claim in BLOCKERS.md, and committed Task 2 (`a000640`).

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | `ebcb21e` | failing records test for the decision rows, the litellm pin and B-09 |
| 2 | `a000640` | decision rows R-136..R-152, CLAUDE.md pin notes, B-09 closed, B-31..B-33 |

## Decision rows

| Id | Subject |
|----|---------|
| R-136 | Index per tenant: `ragflow_{tenant_id}` shared by all datasets, one `q_{dim}_vec` field per dimension, dataset delete removes rows and never the index |
| R-137 | Credential system of record: sealed envelope per `tenant_llm` row (AES-256-GCM, AAD `tenant_id\|provider\|instance`), key rotation re-seals the instance, padding-free envelopes (8095c62), composite ids |
| R-138 | litellm 1.103.2 instead of 1.84.0, no fallback needed; `openai>=2.20,<3`, ollama 0.6.3, xxhash 4.0.1, tiktoken, pycryptodome 3.24.0 |
| R-139 | react-dropzone and @tanstack/react-table not used (D-21) |
| R-140 | Provider base URL and key handling: url_guard policy, DNS-rebinding window and 512-character key pattern cap accepted, test-on-save, limiter, last4 visibility |
| R-141 | Acting workspace rule, API tokens judged as their subject and pinned to the member's own workspace, `me` datasets |
| R-142 | Upload rules: limits, extensions, MIME and magic bytes, `CappedRequest` byte counting (Quart's cap does not check the streamed total), one file per SPA request |
| R-143 | Dedupe and garbage collection, locks, delete ordering, all-or-nothing authorisation, one item per request in the SPA |
| R-144 | Storage layer: interface, MinIO and local drivers, key layout, presigned URLs implemented but exposed by no route |
| R-145 | Doc store port: signature, `_score` on hits, `insert` refuses a missing index, `MatchSparseExpr` NotSupported on Elasticsearch |
| R-146 | API conventions: `{items, total}`, `data.reason`, provider 402 as invalid request, refused provider config is 400 never 401, one 404 body |
| R-147 | Live model tier: marker, gate step, OpenRouter pair, budget, key loaded inside the test process for plan 03-22's vitest journey (T-03-22-04 accepted), fakes elsewhere |
| R-148 | Log masking limit: over-masking of a path word ending in `sk` followed by 20 or more name characters; test markers must not be key-shaped |
| R-149 | Usage counters and log fields `usage_in`/`usage_out`/`usage_total` |
| R-150 | Route generator may tighten `api`/`beta` rows to `jwt`; key-writing and credential-reading rows are session-only |
| R-151 | Locale key prefixes `datasets.files.*` and `datasets.documentDelete.*` instead of `documents.*` |
| R-152 | Shared `AlertDialog` not stacked over a `Dialog` (two Radix dialog copies installed) |

## What changed in CLAUDE.md

- LiteLLM stack row: `1.84.0` to `1.103.2 (exact pin)`, with the reason (two OSV advisories on 1.84.0, none on 1.103.2; D-24, R-138) and the fallback order 1.96.2 then 1.84.0. "Exact pin is mandatory" kept.
- openai row: `2.41.0` to `>=2.20,<3 (locked 2.54.0)`.
- react-dropzone and @tanstack/react-table rows carry "Not installed in Phase 3 ... (R-139)".
- "What NOT to Use" litellm row: `litellm==1.103.2`, fallbacks, and the advisory note.
- The only remaining `1.84.0` mentions are on lines that also name 1.103.2 (the test enforces this).

## What changed in BLOCKERS.md

- B-09 closed (2026-10-10): OpenRouter serves chat and embeddings on one key (D-01, D-06); live tier proven in plan 03-27 with `meta-llama/llama-3.1-8b-instruct` and `baai/bge-m3` (1024 dimensions observed); live Ollama and other providers deferred (D-03); the full clean-room gate with the live step is still plan 03-29.
- B-02 gets an update line: the `vm.max_map_count` reset after host restart is recorded by the summaries of plans 03-03, 03-12, 03-13, 03-14, 03-22 and 03-26.
- B-31 (open): window drop guard and folder-drop case, and focus return after dialogs, covered by jsdom only (plan 03-26 could not make an unguarded page navigate, so no assertion was kept).
- B-32 (open): `forgot-password.test.tsx` (Phase 2) can hit its 5 s timeout at the default vitest worker count under heavy host load; passes alone and with `--maxWorkers=4`.
- B-33 (open, info): host overrides `PREFLIGHT_ALLOW_LOW_MAP_COUNT=1`, `PREFLIGHT_PORTS=`, `LIVE_BASE_URL=http://127.0.0.1:8088`, and the host restarting about five times (orchestrator-reported count).
- B-17, B-21 and B-22 left open (no summary resolves them).

## Verification (real output)

- `uv run pytest test/unit_test/test_phase3_records.py test/unit_test/test_check_decisions.py -q`: `48 passed`.
- `uv run python scripts/ci/check_decisions.py`: `decisions OK: 152 rows`.
- `uv run python scripts/ci/run_all.py`: `7/7 gates passed`.
- `uv run ruff check .`: `All checks passed!`.
- `uv run python run_tests.py -m unit`: `1 failed, 1810 passed, 1 skipped, 885 deselected`. The one failure is outside this plan, see below.
- `git diff -- web/package.json` is empty.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug in the resumed draft] B-02 update named the wrong plans**
- **Found during:** resume review against the summaries
- **Issue:** the draft said plans "03-03 and 03-12 to 03-18" hit the map-count reset; the summaries only record it in 03-03, 03-12, 03-13, 03-14, 03-22 and 03-26.
- **Fix:** the list now matches the summaries. B-33 also gained the restart note, flagged as an orchestrator-reported count.
- **Commit:** `a000640`

### Scope additions

- Five rows beyond the planned twelve (R-148 to R-152), and cross-references in R-19, R-21 and R-50. The test file (Task 1) already required them.

### Deferred (out of scope)

- `test/unit_test/test_clean_room_guard.py::test_without_the_key_the_live_tier_fails_and_does_not_skip` (plan 03-27) fails after 120 s while the stack is down: the subprocess's `ingress` fixture waits for the stack before the missing-key message can fire, so it is not independent of the stack as its docstring says. The stack is down after a host reboot (app container restarting), which this plan's constraints say not to fix. Recorded as item 5 in `deferred-items.md`; the unit tier otherwise has 0 failures.

## Items for the user to review rather than auto-accept

- R-143 / the "all-or-nothing" delete: document deletes authorise and run in one transaction, but a dataset delete only authorises all ids first; the work then goes dataset by dataset, so an infrastructure failure part-way can leave earlier datasets deleted (`data.deleted` lists them). The row says this plainly.
- R-147: the 03-22 vitest journey loads the real OpenRouter key in the test process (accepted threat T-03-22-04, instructed by the orchestrator, not by the plan).
- R-138: the "two OSV advisories on 1.84.0, none on 1.103.2" claim comes from Phase 3 research; no executor re-checked it.
- R-140: DNS-rebinding window and the 512-character key pattern cap are accepted limits.
- R-148: an accepted over-masking in logs.
- R-151 and R-152: the UI-SPEC key names were not followed and a shared component was bypassed; both are workarounds, not fixes.
- B-31: two browser behaviours are unconfirmed outside jsdom.

## Known Stubs

None. This plan edits records and one test only.

## Self-Check

- `test/unit_test/test_phase3_records.py`: FOUND
- `ebcb21e`, `a000640`: FOUND in `git log`
- R-136 to R-152 each present once (the test asserts it)

## Self-Check: PASSED
