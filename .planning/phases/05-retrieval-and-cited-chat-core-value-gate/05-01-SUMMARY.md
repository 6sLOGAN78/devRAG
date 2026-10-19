---
phase: 05-retrieval-and-cited-chat-core-value-gate
plan: 01
subsystem: testing
tags: [decisions, fake-provider, sse, rerank, planted-facts, traceability]
requires: []
provides:
  - "Decision rows R-192..R-202 (R-26 closed, R-27 refined) and the records/traceability tests"
  - "Fake provider: chat_mode, release_chat(), chat_requests(), /rerank (TEI) and /api/v1/rerank (OpenRouter)"
  - "Planted-fact TXT/PDF corpus and controlled-vector rows for the golden fusion test"
  - "Strict-xfail must_not contract case for plan 05-03"
affects: [05-02, 05-03, 05-05, 05-10, 05-11, 05-12, 05-25, 05-28]
tech-stack:
  added: []
  patterns: ["gated SSE stream released by an asyncio.Event set from the test thread", "planted unique-token facts instead of an LLM judge"]
key-files:
  created:
    - test/unit_test/test_phase5_records.py
    - test/unit_test/test_phase5_traceability.py
    - test/unit_test/test_fake_provider_chat.py
    - test/unit_test/test_planted_corpus.py
    - test/helpers/planted.py
  modified:
    - .planning/DECISIONS.md
    - test/helpers/fake_provider.py
    - test/helpers/doc_store_contract.py
key-decisions:
  - "R-192 closes R-26: delta frames, one canonical final frame with reference, then [DONE]; stop is a client abort with the partial persisted in finally"
  - "R-193 refines R-27: markers are 0-based indices into the chunk list placed in the prompt"
  - "R-194..R-202: retrieval route, similarity semantics, query building, rerank fails closed, assistant schema, chat permissions, per-reader unavailable datasets, stopped-turn usage estimate, live budget"
requirements-completed: []
duration: ~45min
completed: 2026-10-19
---

# Phase 5 Plan 01: Records and Test Harness Summary

Wave 0 for Phase 5: decision rows R-192..R-202, a fake provider that can hold, split, record and rerank, and a planted-fact corpus, all in place before any Phase 5 production code.

## Tasks

| Task | Commit | Result |
|------|--------|--------|
| 1. Records and traceability tests, rows R-192..R-202 | 3fd9354 | 11 new rows; R-26 set to accepted and closed by R-192; R-27 refined by R-193; `check_decisions.py` OK (202 rows) |
| 2. Fake provider gated stream, request record, rerank | fa08205 | 10 tests; modes plain, marker, split_marker, gated, error_midstream |
| 3. Planted corpus and controlled vectors | f2ef8e6 | 7 tests; strict xfail `test_must_not_excludes_matches` (ES contract: 50 passed, 1 xfailed) |

## Verification

- `test_phase5_records`, `test_phase5_traceability` (2 gate-only tests skipped without `PHASE5_GATE=1`), `test_fake_provider_chat`, `test_planted_corpus`: 24 passed, 2 skipped.
- `test_llm_drivers.py` (52) and integration `test_llm_bundle_flow.py` (33) still pass; `test_doc_store_es.py` 50 passed, 1 xfailed.
- `check_decisions.py` and `check_no_sleep.py` exit 0.
- The traceability test's 61-id expansion matches all 28 plans: every requirement and D-01..D-26 are already claimed by plan frontmatter.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Stack was down for the integration checks**
- **Found during:** Task 2 verification (connection refused to MySQL/ES).
- **Fix:** brought the stack up with the documented compose command and `scripts/wait_stack.sh`; no code change.

**2. [Rule 3 - Blocking] `pypdf` is not installed in the venv**
- **Found during:** Task 3. The planted-PDF test extracts page text with `pypdfium2` (already used by `rag/parsers/pdf.py`) instead; nothing was installed.

**3. Fixture naming in the new fake-provider test**
- The test defines a local `provider` fixture over `running_fake_provider()` rather than importing `fake_provider`, which ruff flags as F811 when used as a parameter. No change to the shared fixture.

**4. Planted paragraphs are padded to 300 tokens**
- Same sizing rule as `test.helpers.ingest.paragraphs`, so each paragraph is one chunk at the default budget (the plan only said "6-paragraph TXT").

## Known Stubs

None.

## Deferred Issues

- `ruff check test/helpers` reports one pre-existing E501 in `test/helpers/ingest.py:402` (not touched by this plan).

## Next Phase Readiness

Plan 05-03 must remove the `xfail(strict=True)` marker on `test_must_not_excludes_matches` when it implements `must_not`. Later plans append their titles to `REQUIRED_TITLES` in `test_phase5_records.py`; the gate plan (05-28) runs with `PHASE5_GATE=1`.

## Self-Check: PASSED

Files and commits 3fd9354, fa08205, f2ef8e6 verified present.
