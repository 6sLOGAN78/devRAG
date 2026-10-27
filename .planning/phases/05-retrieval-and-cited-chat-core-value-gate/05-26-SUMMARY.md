---
phase: 05-retrieval-and-cited-chat-core-value-gate
plan: 26
subsystem: verification
tags: [chat, citations, browser, live]
requirements-completed: []
completed: 2026-10-27
---

# Phase 5 Plan 26: Real browser core-value journey

The real-provider Chrome journey passes through registration, dataset creation, PDF upload/parse, assistant creation, streamed answer, citation drawer/PDF highlight and reload. Ten distinct nonzero answer lengths prove streaming. Reload preserves the full answer, citation index and source passage. Screenshot: screenshots/phase5-core-source.png. One answer turn and one query embedding, plus the provider-save test. Combined API/browser run: 14 passed in 103.52 s, nine answer turns plus two save tests, 13 query embeddings and two external rerank requests. Four deterministic local-provider scenes pass.

The browser uses the existing standard-library CDP harness and adds no dependency. API-only credential/default setup and temperature zero are the planned exceptions. The observer reads answer content rather than a loading placeholder. Screenshot geometry is tested; user review of wording/alignment remains in 05-HUMAN-UAT.md. R-228 records the measured result.

No source staged or committed. Phase 5 remains in progress pending full timing and final gate. No Phase 4 clean-room completion is claimed.

## Self-Check: PASSED
