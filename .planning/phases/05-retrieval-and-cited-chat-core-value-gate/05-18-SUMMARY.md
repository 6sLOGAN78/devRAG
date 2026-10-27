---
phase: 05-retrieval-and-cited-chat-core-value-gate
plan: 18
subsystem: answer-rendering
tags: [markdown, citations, accessibility, source-gate]
provides:
  - Safe GFM answer renderer with source pills and clipboard code blocks
  - Streaming marker hold-back and code-aware marker utilities
key-files:
  created: [web/src/components/markdown-content/index.tsx, web/src/components/markdown-content/citations.ts, web/src/components/markdown-content/citation-pill.tsx, web/src/components/markdown-content/code-block.tsx, web/src/components/markdown-content/citations.test.ts, web/src/components/markdown-content/message-markdown.test.tsx, web/src/constants/phase5-source-gate.test.ts, web/src/locales/areas/en/chat.json, web/src/locales/areas/zh/chat.json]
  modified: [test/unit_test/test_phase5_records.py, .planning/DECISIONS.md]
requirements-completed: []
completed: 2026-10-26
---

# Phase 5 Plan 18: Safe Answer Rendering

Implemented pure code-aware citation linking and streaming half-marker hold-back. MessageMarkdown renders GFM with the approved packages, escapes raw HTML, emits no image elements, makes only absolute HTTP/HTTPS/mailto links interactive, and looks up sparse citations by their own indices. Unavailable citations are inert locked spans. Source pills have localized accessible names and return their trigger for focus restoration. Tables and code blocks scroll, headings use the body scale, and clipboard copy reports success/failure with a temporary check icon. The source gate protects the rendering, import and package boundaries. R-221 records the rules.

## Verification

The full web unit suite passed 1851 tests across 91 files with maxWorkers=4. Type checking, production build, locale parity, copy/source gates, records and decision validation passed. Focused tests cover hostile HTML, unsafe/relative links, tracking images, sparse/unavailable citations, code markers, streaming tails, GFM and clipboard rejection. No package or commit was added in this plan. UI-22 remains Partial as explicitly approved at R-217.

## Self-Check: PASSED
