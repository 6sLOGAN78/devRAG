---
phase: 05-retrieval-and-cited-chat-core-value-gate
plan: 06
subsystem: retrieval-calibration
tags: [calibration, similarity-threshold, bge-m3, probe, retrieval]
requires:
  - phase: 05-04
    provides: "POST /api/v1/datasets/search with similarity, term_similarity and vector_similarity per hit"
  - phase: 05-01
    provides: "planted-fact corpus (test/helpers/planted.py)"
provides:
  - "scripts/probe/calibrate_retrieval.py: manual live calibration run plus pure summarise, decide and pick_sample functions"
  - "05-CALIBRATION.md: measured term, vector and blended similarity for 10 samples, weight probes and the planted-fact wording"
  - "Outcome keep: the default similarity threshold stays 0.2, now backed by measurement"
  - "Decision row R-208"
affects: [05-11, 05-13, 05-19, 05-24, 05-25]
tech-stack:
  added: []
  patterns: ["one-off probe scripts live in scripts/probe and are not collected by pytest", "evidence is rendered from an allow-list of fields and checked against the key before it is written"]
key-files:
  created:
    - scripts/probe/__init__.py
    - scripts/probe/calibrate_retrieval.py
    - test/unit_test/test_probe_calibration.py
    - .planning/phases/05-retrieval-and-cited-chat-core-value-gate/05-CALIBRATION.md
  modified:
    - test/unit_test/test_phase5_records.py
    - .planning/DECISIONS.md
key-decisions:
  - "R-208: threshold 0.2 kept; relevant (paraphrased, no token) 0.2867..0.6381, irrelevant 0.0783..0.1221, planted-fact wording 0.6796..0.7979"
patterns-established:
  - "decide(summary, current, margin) returns keep, change (midpoint rounded to 0.05, clamped to [0.05, 0.6]) or blocked (ranges overlap)"
requirements-completed: []
duration: ~1h
completed: 2026-10-20
---

# Phase 5 Plan 06: Retrieval Threshold Calibration Summary

The default similarity threshold of 0.2 was checked against real `baai/bge-m3` vectors on the planted corpus and kept: every irrelevant question scored at most 0.1221 and every relevant one at least 0.2867, so the empty-response path and the planted-fact tests have a margin on both sides.

## Tasks

| Task | Commit | Result |
|------|--------|--------|
| 1. Probe script with unit-tested summary and decision rule | b986228 | `calibrate_retrieval.py` (manual live run, 24-query budget counter, allow-listed evidence, retry by deadline polling on 429/502/503/504); `summarise`, `decide`, `pick_sample`, `render_evidence`; 16 unit tests |
| 2. Run the probe, record the evidence, apply the rule | a407ac7 | `05-CALIBRATION.md`, row R-208, `Calibration result` in REQUIRED_TITLES; outcome `keep`, no code default changed |

## Measured result

Blended similarity (weight 0.3, threshold 0, rerank off), 7 chunks in 2 documents:

| Group | Min | Max | Mean |
|-------|-----|-----|------|
| relevant (5, worded without the planted token) | 0.2867 | 0.6381 | 0.4400 |
| irrelevant (5: off-topic, nonsense string, other domain, stopwords only, greeting) | 0.0783 | 0.1221 | 0.1045 |

The planted-fact test wording (token included, 5 questions) scored 0.6796 to 0.7979. Rule check: 0.1221 is below 0.15 and 0.2867 is at or above 0.25, so the outcome is `keep`. The relevant side has the thinner margin (0.037 above T + 0.05) for paraphrased questions with little shared vocabulary; the D-07 tests use token-bearing questions and sit far higher.

Spend: 19 query embeddings of the 24 allowed (5 relevant, 5 irrelevant, 4 weight probes, 5 supplementary), plus the provider save test call and the ingestion of 7 chunks. No chat call. All outside the D-06 gate budget.

## Verification

- `test/unit_test/test_probe_calibration.py`, `test_phase5_records.py`, `test_schema_export.py`: 25 passed. `check_decisions`: 208 rows. `check_secrets`: OK. `ruff check` on the new files clean.
- `grep -c 'sk-'` on the evidence file prints 0; `git status --short docker/.env` prints nothing; the script's only `print` calls are the missing-key message and the outcome line (no key variable).
- `pytest --collect-only scripts` collects nothing from `scripts/probe`.
- Live run against the dev stack on port 8088 completed in one attempt; no provider retry was needed.

## Deviations from Plan

### Auto-fixed Issues

None.

### Choices the plan left open

- **Embedding model only in the provider save.** The plan text says "chat and embedding models", but the run rules forbid chat calls and saving a chat model makes a test call. The probe saves the embedding model only; retrieval needs nothing else.
- **Supplementary samples.** Besides the 10 required samples and the 4 weight probes, the probe asked the five token-bearing D-07 questions (19 embeddings in total, inside the 24 cap) to confirm the planted-fact tests are not threshold-starved. They are reported separately and do not enter the decision.
- **Decisive chunk.** A relevant sample is the best chunk that holds the planted token (zero if that chunk is not returned); an irrelevant sample is the best chunk of the whole answer. `decide` treats the irrelevant bound as strict and the relevant bound as inclusive, as the plan states.
- **`change` equal to the current value** is possible by the rule (midpoint rounds back to T) and means no code change; documented in `decide`.

## Known Stubs

None.

## Deferred Issues

None.

## Threat Flags

None beyond the plan's register. T-05-06-01: the key is read by `stack_env()`, sent only in the provider PUT body, never printed, and the evidence text is checked against it before writing. T-05-06-02: `QueryBudget` aborts above 24 (19 used). T-05-06-03: no threshold changed; the number and rule are in R-208.

## Next Phase Readiness

Plans 05-11 (turn orchestration), 05-19 (assistant dialog) and 05-24 (retrieval page) keep 0.2 as the default. Empty-response tests can use any off-topic question (all five scored below 0.13); planted-fact tests can assume the fact chunk scores well above 0.2.

## Self-Check: PASSED

Files verified present (`scripts/probe/calibrate_retrieval.py`, `scripts/probe/__init__.py`, `test/unit_test/test_probe_calibration.py`, `05-CALIBRATION.md`); commits b986228 and a407ac7 verified in git log.
