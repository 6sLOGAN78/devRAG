---
phase: 04-ingestion-pipeline
plan: 01
subsystem: planning-records
tags: [decisions, layering, requirements]
requires: []
provides:
  - decision rows R-154..R-167 and resolved R-11
  - layering carve-out for rag/svr
affects: [all Phase 4 plans]
key-files:
  created: [test/unit_test/test_phase4_records.py]
  modified: [.planning/DECISIONS.md, .planning/REQUIREMENTS.md, .planning/ROADMAP.md, test/unit_test/test_layering.py]
decisions:
  - "R-154..R-167 recorded; R-11 resolved by R-155"
metrics:
  tasks: 2
  files: 5
  completed: 2026-10-17
---

# Phase 4 Plan 01: Decision records and layering carve-out Summary

Fourteen Phase 4 decision rows (R-154..R-167) written and pinned by a contract test, R-11 resolved by R-155, four partial requirements and the Phase 6 hand-off recorded, and the layering test split so only `rag/svr` may import `api.db`.

## Tasks

| Task | Commit | Notes |
|------|--------|-------|
| 1 Records test and rows | 6ab0cc9 | RED seen (5 failed) before rows existed |
| 2 Partial notes and layering | f0f1459 | CHUNK-17, PARSE-09, PARSE-11, UI-14 partial |

## Deviations from Plan

- The plan's task text says "thirteen rows" in places and LAST_ROW 166 in one behavior line; the action lists 14 (R-154..R-167), which was followed.
- The venv `pytest` script has a stale shebang (old path); tests run with `uv run python -m pytest`.
- Traceability table rows for the four requirements were also changed from Pending to Partial.

## Known Stubs

None.

## Self-Check: PASSED

Both commits exist; 14 tests pass; `scripts/ci/check_decisions.py` reports 167 rows OK.
