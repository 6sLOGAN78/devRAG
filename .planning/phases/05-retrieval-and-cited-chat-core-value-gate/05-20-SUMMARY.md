---
phase: 05-retrieval-and-cited-chat-core-value-gate
plan: 20
subsystem: chat-page
tags: [routing, workspace, pagination, accessibility]
provides:
  - Signed-in chat route, legacy redirect and navigation entry
  - Workspace-bound URL selection, assistant rail, personal chat list and page states
requirements-completed: []
completed: 2026-10-26
---

# Phase 5 Plan 20: Chat Page Shell

Added /chats and the /chat redirect, with Chat third in Platform navigation and System status fourth. The assistant and personal chat lists support 20-row pages, debounced search, initials and visibility, independent retries and focus-preserving pagination. The URL validates both ids before requests; auto-selection replaces history, choosing an assistant clears session, and New chat keeps a draft. Workspace switching fences the previous ids until URL clearing completes, including intermediate renders. Empty, loading, gone and error states are implemented. The mobile rail is a left sheet; it fully closes before creating an assistant. Dialog focus returns to its opener or the surviving mobile trigger. R-223 records the contract.

## Verification

The full frontend suite passed **1951 tests in 96 files** with maxWorkers=4. Final focused verification after page-clamping and workspace-guard refinements passed **85 tests in 7 files**, including 18 rail tests, 11 page tests, dialog confirmations introduced for the next plan, locale/copy/source gates. TypeScript and the production build passed. Phase 5 records passed (3 tests), decisions validated (223 rows), and git diff --check was clean. Existing navigation tests were updated to the actual built routes. No dependency or commit was added by this plan.

## Self-Check: PASSED
