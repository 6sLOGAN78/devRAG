---
phase: 05-retrieval-and-cited-chat-core-value-gate
plan: 14
subsystem: dependency-approval
tags: [npm, audit, tei, human-checkpoint]
provides:
  - Human-approved exact SSE and Markdown dependency pins
  - TEI image/model and UI scope approval
key-files:
  created: [web/src/constants/phase5-packages.test.ts, .planning/phases/05-retrieval-and-cited-chat-core-value-gate/05-PACKAGES.md]
  modified: [web/package.json, web/package-lock.json, test/unit_test/test_phase5_records.py, .planning/DECISIONS.md]
requirements-completed: []
completed: 2026-10-26
---

# Phase 5 Plan 14: Approved Packages

Recorded the user's verbatim approval, installed eventsource-parser 4.1.2, react-markdown 10.1.0 and remark-gfm 4.0.1, and added an exact dependency-set gate. The actual lockfile matches all 98 audited new entries, changes no existing version and removes none. The user also accepted GFM-only UI-22 Partial scope, the TEI provider and rerank type, and the TEI image/model for plan 05-15. R-217 records the outcome and R-206 records confirmation.

## Verification

The package gate failed before installation and passed afterwards. The production build, 22 constants tests, 3 phase-record tests and decision validation passed. Python dependency files remain unchanged. npm reports seven advisories in previously locked dependencies; none affects a newly added lockfile entry. This is recorded in the audit rather than upgrading unrelated packages.

The separately approved unused Docker build cache cleanup reclaimed 3.355 GB and left 8.4 GB free. Plan 05-15 will recheck capacity before download. No TEI image/model was pulled here. Changes remain uncommitted under the plan's instruction.

## Self-Check: PASSED
