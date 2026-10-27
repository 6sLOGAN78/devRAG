---
phase: 05-retrieval-and-cited-chat-core-value-gate
plan: 24
subsystem: retrieval-testing
tags: [retrieval, scores, workspace, pagination]
provides:
  - Dataset retrieval testing page, explicit-run controls and ranked score cards
  - Workspace-bound request snapshots, pagination, source drawer and dataset entry link
requirements-completed: []
completed: 2026-10-26
---

# Phase 5 Plan 24: Retrieval Testing

Added the signed-in dataset subpage and Test retrieval entry before Upload files. The page waits for dataset binding and the matching active workspace, then offers bounded questions, calibrated threshold/weight controls and optional rerank. Only Run or pagination sends a search; each explicit rerun gets a new run id, while edits/reset mark retained results stale. Questions stay in local state and never enter the URL. Ranked cards show finite/null scores, an accessible overall bar, measured passage expansion, rerank-only fields and the shared source drawer. Idle, running, empty, unparsed, forbidden, missing-dataset and fixed-error states are implemented.

Two integration requirements extended the earlier service work: the timing mapper retains embed_ms, and search bodies receive the active tenant_id (including joined-workspace deep links). The dataset detail's existing chunkNum view supplies the unparsed notice. R-226 records the results. The existing empty-dataset test now waits for the page's sole Upload action after the header/empty-state handoff. A localization-key expression was rewritten to satisfy the unchanged secrets heuristic.

## Verification

Final full frontend suite: **2135 tests across 105 files passed**, maxWorkers=4. TypeScript and production build passed. Retrieval coverage includes 28 control/card/page cases and 16 refusal cases; route and member-entry assertions pass. The prior full attempt exposed the upload-action timing assertion; its wait and missing helper import were corrected before the final passing run. Nine Python helper/record tests passed, helper Ruff passed, decisions validated (226 rows), secrets/no-sleep gates and git diff --check passed. No dependency change or commit.

## Remaining gate

Plan 05-15 still requires the B-37 reranker/model decision; live and real-browser exit proofs remain pending. The older running app image has not been rebuilt with these local frontend changes. See 05-25-PROGRESS.md for the prepared stream helper and capacity checkpoint.

## Self-Check: PASSED
