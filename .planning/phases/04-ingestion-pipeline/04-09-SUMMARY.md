---
phase: 04-ingestion-pipeline
plan: 09
subsystem: ingestion
tags: [parsers, docx, xlsx, pptx, html, zip-bomb, xxe]
requires:
  - phase: 04-02
    provides: approved Office and HTML packages
  - phase: 04-06
    provides: parser contract, router, txt decode helper
provides:
  - check_ooxml_limits archive and entity guard
  - DOCX, XLSX, PPTX, HTML parsers (rag.parsers.docx/xlsx/pptx/html)
  - test/helpers/office_files.py builders
affects: [04-worker pipeline, 04-35]
tech-stack:
  added: []
  patterns: [guard-before-open, fixed-message typed errors, eager extraction so errors raise at call time]
key-files:
  created:
    - rag/parsers/{limits,docx,xlsx,pptx,html,tabletext}.py
    - test/helpers/office_files.py
    - test/unit_test/{test_parsers,test_ooxml_limits}.py
  modified: []
key-decisions:
  - "The guard refuses any XML part holding DOCTYPE or ENTITY (case-insensitive, bounded 8 MiB read) because lxml entity defaults were not verified (A6)"
  - "Parsers extract eagerly and return an iterator, so typed errors raise at call time (04-06 convention)"
  - "Zero compressed size with non-zero declared size counts as a limits violation"
requirements-completed: []
duration: ~25min
completed: 2026-10-17
---

# Phase 4 Plan 09: Office and HTML parsers with OOXML guard

`check_ooxml_limits` runs before every Office parser and refuses too many members, oversize totals or members, ratios above 200, and any DOCTYPE or ENTITY declaration. DOCX, XLSX, PPTX and HTML parsers sit behind it on the shared `parse(...)` contract.

## Tasks

1. Archive guard and generated files: RED 0db7116, GREEN 3b79e84
2. Four parsers: RED 87cac4c, GREEN cfc9e7a

31 tests pass (parsers, guard, router); `scripts/ci/run_all.py` 7/7; ruff clean on touched files; no warnings.

## Deviations from Plan

- [Rule 3 - structure] Added `rag/parsers/tabletext.py` (one `render_table` helper) so DOCX, XLSX and PPTX share escaped HTML table rendering instead of duplicating it. No new dependency.
- XLSX header-only sheets yield one block holding just the header, so a sheet is never silently dropped.
- Damaged-file wrapper also catches `AttributeError` (library internals on malformed parts), mapped to `FileDamaged` with no original text.

## Known Stubs

None. Images are skipped and counted by design (D-27).

## Threat Flags

None. T-04-09-01 to -04 mitigated and tested (ratio bomb at 3 MiB, `file:///` entity payload, script/style removal with no `<` in output, path not in error messages).

## Self-Check: PASSED
- All created files exist; commits 0db7116, 3b79e84, 87cac4c, cfc9e7a present.


## Security hardening (post-review)

OOXML findings 3 to 5: every XML-looking member scanned whole in overlapping 1 MiB windows regardless of extension, UTF-16/32 and non-UTF-8 declared encodings rejected. Commits 6a6eaf1 (tests) and 96d0c91 (fix). Decision R-168.
