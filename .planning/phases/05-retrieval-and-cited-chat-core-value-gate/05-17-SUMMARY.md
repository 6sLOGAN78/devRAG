---
phase: 05-retrieval-and-cited-chat-core-value-gate
plan: 17
subsystem: web-chat-hooks
tags: [react-query, cancellation, test-server]
provides:
  - Workspace-scoped assistant/session queries and mutations
  - Streaming turn hook with authoritative refresh and cancellation
  - Assistant, chat and retrieval test-server areas
key-files:
  created: [web/src/hooks/use-chat-request.ts, web/src/hooks/use-chat-request.test.tsx, web/src/hooks/use-retrieval-request.ts, web/src/test/server-areas/assistants.ts, web/src/test/server-areas/chat.ts, web/src/test/server-areas/retrieval.ts]
  modified: [web/src/test/dataset-server.ts, web/src/test/server-areas.test.ts, web/src/services/sse.ts, web/src/services/sse.test.ts, web/src/hooks/use-llm-request.ts, .planning/DECISIONS.md]
requirements-completed: []
completed: 2026-10-26
---

# Phase 5 Plan 17: Hooks and Test Server

Implemented workspace-prefixed query keys, known-workspace/32-hex resource gating, same-workspace/resource paged placeholders, non-retried mutations and settled invalidation. The turn hook rejects pre-stream refusals, keeps partial output on errors/stops, ignores duplicate sends, aborts on navigation/unmount and refreshes stored data. A first draft session id can enter the URL without cancelling its turn. Retrieval is a non-retried mutation and rerank model queries work through the widened model type.

The three auto-registered test-server areas provide assistant sharing/binding rules, private sessions and 50-message cursor paging, sparse references, feedback, deterministic retrieval, and controllable fetch streams. The existing forced-failure helper gained optional typed data for counts/dataset ids.

## Verification

The complete web unit suite passed 1787 tests across 88 files with maxWorkers=4; type checking, production build, records, decision and no-sleep gates passed. Two added regression cases failed before fixing a 401 being masked by purge-triggered cancellation and an old stream continuing after another session was selected; both now pass. R-220 contains the hook/test-server amendment.

Plan 05-15 remains blocked by B-37 and the additional model decision is pending. No new package or commit was made in this plan.

## Self-Check: PASSED
