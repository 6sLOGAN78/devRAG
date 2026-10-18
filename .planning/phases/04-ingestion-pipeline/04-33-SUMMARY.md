---
phase: 04-ingestion-pipeline
plan: 33
subsystem: testing
tags: [live_model, e2e, embeddings, openrouter, bge-m3, elasticsearch, leak-scan]
requires:
  - phase: 04-22
    provides: executor container journeys and shared ingest helpers
  - phase: 03-27
    provides: live_model tier, live_env and ingress fixtures
provides:
  - test/testcases/test_live_ingestion.py (11 tests, live_model only)
  - pdf_chunk_config, expected_pdf_chunks, small_live_files in test/helpers/ingest.py
  - guard tests for both live files (fixed failure message, no skip, marker)
affects: [clean-room gate]
tech-stack:
  added: []
  patterns: [model-tier fixtures imported by name, offline expectation computed with the real parser and chunker, results reduced to booleans and counts before asserting]
key-files:
  created:
    - test/testcases/test_live_ingestion.py
  modified:
    - test/helpers/ingest.py
    - test/unit_test/test_clean_room_guard.py
key-decisions:
  - "R-182: the live PDF budget is three longest lines plus four tokens (25), so the PDF yields 26 chunks; the offline count is the oracle"
requirements-completed: []
duration: about 50 min
completed: 2026-10-19
---

# Phase 4 Plan 33: Live ingestion tier Summary

**A 13-page PDF and five small files are parsed through the real stack with real `baai/bge-m3` vectors; vector shape, nearest-neighbour placement, edit, add, confirmed re-parse, the poison file and a key leak scan all pass in 11 tests.**

## What was built

- `test_live_ingestion.py` (`live_model` only): saves the OpenRouter provider through the API, sets the default embedding model, creates a 1024-dimension dataset, uploads the PDF and a TXT, DOCX, XLSX, PPTX and HTML file, patches the PDF `parser_config`, parses all six with one request and waits for run 3.
- Checks: stored count equals the offline count and the index; two task rows `(0,12)` and `(12,13)`; positions on pages 1 to 13; every vector has 1024 numbers and norm 1.0 within 1e-6; a page-7 sentence and a DOCX table sentence each find their own chunk as the top hit; `used_tokens` grew from 0; edit changes the vector (cosine below 0.999999) and is found by a dense search; add is found the same way; the unconfirmed re-parse answers 409 with `edited_count 1`, `manual_count 1`; the confirmed re-parse restores the original count; a damaged DOCX ends `file_damaged` with 3 retries and no token use; the key (or any 12-character window of it) is absent from all recorded responses, task progress lines, ingestion log rows and the executor and app logs.
- Helpers: `pdf_chunk_config()`, `expected_pdf_chunks()` (runs the real PDF parser and naive chunker offline over the same two page ranges the executor uses), `small_live_files()`.
- Guard: `test_clean_room_guard.py` now parametrises the file rule and the no-key rule over both live files; `scripts/clean_room.sh` is untouched.

## Live run result (real OpenRouter key present, run twice, both passed)

| File | Chunks (index = chunk_count = offline) |
|---|---|
| live-thirteen.pdf | 26 (bounded 20..40) |
| live-notes.txt | 5 |
| live-report.docx | 4 |
| live-sheet.xlsx | 5 |
| live-deck.pptx | 5 |
| live-page.html | 5 |
| Parse total | 50 |

Embedded chunks over the whole file: 50 + 1 edit + 1 add + 5 TXT re-parse = 57 of the 72 cap. Dataset `chunk_num` equalled the per-document sum. `used_tokens` after the first parse: 7979. Leak scan covered 68 to 72 recorded responses, 8 progress lines, 8 log rows and the executor and app logs, with 0 hits. No key or fragment is recorded here.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan formula gave 39 PDF chunks, not 26**
- **Found during:** Task 1
- **Issue:** `chunk_token_num = 3 x longest line (7)` is 21, but the two line breaks between three lines make a 3-line chunk 23 tokens, so only two lines fit per chunk (39 chunks, leaving 71 of 72 with the other files).
- **Fix:** `pdf_chunk_config()` returns `3 x longest + 4` (25); the PDF then yields 26 as the plan states, and the test still asserts equality with the offline count and the 20..40 bound.
- **Files modified:** test/helpers/ingest.py
- **Commit:** 7feac9e

**2. [Rule 3 - Blocking] `# fmt: skip` comments broke the "no skip text" rule**
- Removed them and formatted the file with ruff instead; added a module-level `pytest.fail(` guard fixture (`key_present`) so the file itself carries the fixed message.

The DOCX yields 4 chunks, not 5: its table text merges into the fourth paragraph's chunk (inside the plan's "about 5, at most 10").

## Deferred Issues

- `uv run python scripts/ci/run_all.py` exits 1 (6 of 7 gates): `no_sleep` flags `web/src/pages/dataset/ingestion-summary.test.tsx:87` (plan 04-26 file, not touched here). Logged in `deferred-items.md`; the acceptance line "run_all exits 0" for Task 2 is therefore not met by this plan's own changes.
- `test/helpers/ingest.py` was already not ruff-formatted before this plan; not reformatted.

## Auth gates

None. The key was present in `docker/.env`.

## Known Stubs

None.

## Threat Flags

None.

## Self-Check: PASSED

- test/testcases/test_live_ingestion.py present; commits 7feac9e and b113994 exist.
