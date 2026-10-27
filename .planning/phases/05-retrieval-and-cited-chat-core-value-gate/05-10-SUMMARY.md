---
phase: 05-retrieval-and-cited-chat-core-value-gate
plan: 10
subsystem: chat-prompts
tags: [citations, prompts, context, history, injection]
requires:
  - phase: 05-01
    provides: "citation marker and decision contracts"
  - phase: 05-02
    provides: "retrieval settings and candidate chunks"
provides:
  - "Pure citation normalisation, validation, history stripping and embedding fallback"
  - "Deterministic context blocks, history trimming, token budget and prompt assembly"
affects: [05-11, 05-12, 05-13, 05-19, 05-23]
tech-stack:
  added: []
  patterns:
    - "One compiled marker pattern and one immutable citation rules string"
    - "Context indices assigned after dedupe and token trimming"
key-files:
  created:
    - rag/prompts/__init__.py
    - rag/prompts/citations.py
    - rag/prompts/generator.py
    - test/unit_test/test_citations.py
    - test/unit_test/test_prompt_context.py
  modified:
    - test/unit_test/test_phase5_records.py
    - .planning/DECISIONS.md
key-decisions:
  - "R-213 records the block format, 0.97 budget, history rule and prompt injection stance"
patterns-established:
  - "Prompt construction is pure and accepts injected token counting and embedding callables"
requirements-completed: []
duration: one session
completed: 2026-10-25
---

# Phase 5 Plan 10: Prompt and Citation Core

Citation markers now have one canonical pattern. Model variants are normalised outside code, invalid indices are removed, and a deterministic sentence embedding fallback can cite uncited answers. Context blocks are deduplicated and trimmed before numbering; history is bounded and stripped of old markers. The system prompt separates editable instructions from fixed citation and injection rules.

## Verification

The plan's unit and record suite passed 59 cases: 34 citation cases, 22 context and prompt cases, and 3 decision record cases. Ruff, `git diff --check` and all 7 CI gates passed. `rag/prompts/citations.py` defines one compiled marker pattern; `rag/prompts/generator.py` imports it and has no compiled pattern of its own.

## Hand-off

Plan 05-11 can use `ContextBuild.used` to build references in the same order the model saw, `assemble_prompt` for the final system and message payload, and `canonicalise` plus `insert_citations` before storing an answer. Changes remain uncommitted under the plan's explicit `do not commit` instruction. Phase requirements remain unticked pending phase verification.
