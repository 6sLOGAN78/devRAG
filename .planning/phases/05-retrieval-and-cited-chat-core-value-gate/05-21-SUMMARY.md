---
phase: 05-retrieval-and-cited-chat-core-value-gate
plan: 21
subsystem: saved-conversations
tags: [messages, deletion, permissions, accessibility]
provides:
  - Conversation header, per-reader dataset notice and standalone delete confirmations
  - Saved message rendering, derived greeting and anchored history paging
requirements-completed: []
completed: 2026-10-26
---

# Phase 5 Plan 21: Saved Conversations and Confirmations

The header shows the assistant, visibility and role-appropriate settings/menu actions. Delete actions open standalone confirmations after the non-modal menu closes. Assistant deletion refreshes the teammate count before enabling confirmation, preserves a cached count if refresh fails, and handles an already-gone assistant. Busy confirmations resist repeated submission, Escape and dismissal. Successful deletion returns to a draft or another assistant. Per-reader dataset notices distinguish skipped from wholly unavailable bindings.

Stored messages render literal user text and safe Markdown answers with sparse citation lookup, finish-state lines, measured/estimated metadata and a derived greeting. The newest 50 load first; earlier pages prepend with the previous first message anchored. Refresh retains stopped content. Parent gone handling is suspended during settings/deletion so an accepted visibility change completes its own success path before selecting another assistant. R-223 was amended, with no new decision row.

## Verification

Full frontend suite: **1992 tests across 98 files passed**, maxWorkers=4. TypeScript, production build, locale/copy/source gates, record tests and 223-row decision validation passed. Focused coverage includes 21 confirmation/header cases, 13 message-list cases and 18 page cases, including settings focus return, deletion navigation, stored refresh and non-creator narrowing through the full page. No dependency change or commit.

## Self-Check: PASSED
