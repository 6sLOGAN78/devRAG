---
phase: 05-retrieval-and-cited-chat-core-value-gate
plan: 22
subsystem: streaming-conversation
tags: [sse, input, stop, accessibility, scroll]
provides:
  - IME-safe message input, typed refusals and exact draft restoration
  - Streaming conversation, stop/reconciliation, live announcements and scroll following
requirements-completed: []
completed: 2026-10-26
---

# Phase 5 Plan 22: Streaming Conversation

MessageInput supports Enter/Shift+Enter/IME/Escape, a focusable readOnly busy field, bounded height, the character counter and limit, Send/Stop accessible names and draft restoration. Refusals map by HTTP status/reason and ApiError.kind to fixed localized copy. Conversation appends deltas, hides incomplete citation markers, replaces the final canonical text, preserves partial failed/stopped text, writes the first session id without aborting, and reconciles with authoritative refetched messages. The polite region announces only state transitions. Scrolling follows only while near the end; sending/jumping forces the end, reduced motion is instant, and earlier-history anchoring suspends auto-follow.

A timing regression uncovered an additional necessary hook change: useChatTurn exposes transport pending separately from the terminal frame, keeping Send guarded until DONE. A test holds the transport after the final answer. Repeated identical refusals restore drafts independently; connection loss retains partial text without exposing an exception sentence. R-224 records the rules.

## Verification

Full frontend suite: **2054 tests across 101 files passed**, maxWorkers=4. TypeScript and production build passed. Focused tests cover 28 streaming/scroll cases, 15 input cases and 19 refusal cases. Locale/copy/source gates, three record tests, 224-row decision validation and git diff --check passed. No dependency change or commit.

## Self-Check: PASSED
