---
phase: 05-retrieval-and-cited-chat-core-value-gate
plan: 19
subsystem: assistant-dialog
tags: [assistant, sharing, forms, accessibility]
provides:
  - Create and settings dialog with changed-fields saves and sharing restrictions
  - Bounded avatar picker, paged dataset checklist, range control and permission helper
requirements-completed: []
completed: 2026-10-26
---

# Phase 5 Plan 19: Assistant Dialog

Implemented the create/settings dialog with localized validation, all four field groups, exact defaults, changed-fields settings writes and role-aware model setup. Dataset options load every page and sort by name. Private/shared combinations have visible reasons; hidden bindings stay linked through visible-only saves. Server refusals map to fields or plural inline alerts, including both supported model-unavailable HTTP statuses. Successful non-creator narrowing reports that the assistant left the editor's list. A fresh mounted body and pending ref isolate each opening; Close remains available during saves, duplicate submission and pending Escape/overlay dismissal are guarded.

Avatars decode and cover-crop to a 128 by 128 PNG canvas with bounded PNG/JPEG preview validation and initials fallback. Range inputs retain native keyboard semantics. Disabled dataset reasons are linked to the checkbox. The server default instruction equals the English form prefill; citation rules retain their pinned digest. R-222 records UI-25 and CHAT-05 Partial scope.

## Verification

Full frontend unit suite: **1922 tests across 94 files passed**, maxWorkers=4. The assistant suite has 55 tests, covering role-specific blocked forms, narrowing, hidden bindings, every error mapping, multiple dataset pages, image save, pending close/reopen isolation and focus. Production build and TypeScript passed. Python prompt parity, context, citation digest and record tests: **27 passed**; decision validation: **222 rows**. No package change or commit was added by this plan.

## Self-Check: PASSED
