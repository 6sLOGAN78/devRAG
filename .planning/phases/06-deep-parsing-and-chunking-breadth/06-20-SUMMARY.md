---
phase: 06-deep-parsing-and-chunking-breadth
plan: "20"
subsystem: document-metadata
requirements-completed: []
---

# Plan 06-20: Edit and inspect bounded document metadata

A member can edit selected documents' bounded metadata by merge or replace, inspect a deterministic paged flattened inventory across authorized datasets, and read the dataset's auto metadata configuration. Migration 0005 adds durable JSON metadata; parsing, manual chunks and public document views carry it without changing source text or geometry. Checked index writes synchronize the current chunks. The selected-document UI supports field errors, refetch and stale-workspace fencing.

An original annotation and intentional behavioral RED were retained. Real MySQL migration 14, marked unit 2597/8 existing skips, full web 2186/113 files, affected services 98, live integration 2 including reparse, rebuilt Chrome 1, affected document flow 23, tenant matrix 17, Go, CI 7/7 and records 5 passed. The actual Chrome metadata manager screenshot was inspected. Current app/worker/native image IDs matched healthy containers after rebuilding. See `06-20-VERIFICATION.json` for hashes and logs.

Inline review records the cross-store partial-write limit and corrections made before the final gate. No new package/model, paid external call or local ASR submission. R251 accepted automatically, not user-reviewed. REQUIREMENTS checkboxes remain untouched. Phase5 human acceptance, Phase4 B36, and final Phase6 gate/UAT remain pending. Continue Plan21 generated keywords and questions.
