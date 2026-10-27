---
phase: 05-retrieval-and-cited-chat-core-value-gate
plan: 13
subsystem: live-citation-adherence
tags: [live-model, citations, evidence, model-choice]
requires:
  - phase: 05-06
    provides: "Calibrated retrieval settings and live provider setup"
  - phase: 05-12
    provides: "Completion route and stored cited turns"
provides:
  - "Unit-tested one-off live citation adherence probe and fixed switch rule"
  - "Fifteen real 8B model answers with evidence and a keep decision"
affects: [05-14, 05-25, 05-26]
tech-stack:
  added: []
  patterns:
    - "Evidence allows controlled labels, indices and counts only"
    - "CITATION_RULES digest pins the measured prompt"
key-files:
  created:
    - scripts/probe/citation_adherence.py
    - test/unit_test/test_probe_adherence.py
    - test/unit_test/test_citation_rules_pinned.py
    - .planning/phases/05-retrieval-and-cited-chat-core-value-gate/05-ADHERENCE.md
  modified:
    - scripts/probe/calibrate_retrieval.py
    - test/unit_test/test_phase5_records.py
    - .planning/DECISIONS.md
key-decisions:
  - "R-216 keeps the 8B chat model after 15/15 planted citations and zero raw no-marker answers"
requirements-completed: []
duration: one session
completed: 2026-10-26
---

# Phase 5 Plan 13: Live Citation Adherence

The probe asked five planted-fact questions three times each through the real completion route with the configured `meta-llama/llama-3.1-8b-instruct` and temperature 0. All 15 answers cited the planted chunk and included the numeric fact. No answer lacked a raw valid marker and none needed fallback insertion. The fixed rule therefore keeps the 8B model; no model default changed. The probe made 15 of its 20 allowed completion calls.

The evidence lists only planted labels, run numbers, valid marker indices and counts. A key-presence check confirmed that the provider key is absent. The citation rules are pinned by SHA-256; changing them requires a new probe.

## Verification

The probe and decision tests, citation-rules pin, phase-record and environment-catalog suites passed 27 cases. Ruff, `git diff --check`, decision validation and the secrets gate passed. The live probe completed successfully and wrote 15 result rows to `05-ADHERENCE.md`.

Changes remain uncommitted under the plan's `do not commit` instruction. Phase requirements remain unticked pending phase verification.
