---
phase: 05-retrieval-and-cited-chat-core-value-gate
plan: 23
subsystem: sources-and-feedback
tags: [citations, preview, feedback, accessibility]
provides:
  - Shared source drawer for sparse chat references and ranked retrieval hits
  - Source chips and authoritative completed-answer feedback
requirements-completed: []
completed: 2026-10-26
---

# Phase 5 Plan 23: Source Drawer and Feedback

The shared right-hand drawer focuses the saved passage, shows present finite scores, and reuses PagePreview for stored PDF positions with boxes and page selection. Page images use the existing authenticated blob fetch. A document-detail 404 keeps the saved passage and removes the original-document link; unavailable references cannot open. Body state resets on close/source change. Chat citations and 40/44 px source chips open the same sparse-indexed source; refetch preserves the chosen index and a fresh redaction closes the drawer. Focus returns to the logical pill or chip even when Markdown rerendering replaced its DOM node. Stream completion respects an open drawer's focus and header overlays are guarded.

Feedback appears only on complete non-empty answers, saves without optimistic state, clears a pressed rating, guards repeated requests and uses fixed failure copy. Added source locales plus four shared retrieval-score labels needed by both the drawer and the next plan. UI-SPEC avatar-input/visibility test ids and instruction textarea sizing were aligned. R-225 records these outcomes.

## Verification

Full frontend suite: **2089 tests across 103 files passed**, maxWorkers=4. TypeScript, production build, locale/copy/source gates, prompt parity and citation digest checks passed. Source drawer has 17 tests and citation/feedback has 18, including authenticated image requests without URL tokens, deletion, image retry, redaction, sparse refetch, focus return and streaming-focus preservation. Five Python checks passed; decisions validated (225 rows); git diff --check clean. No dependency change or commit.

## Self-Check: PASSED
