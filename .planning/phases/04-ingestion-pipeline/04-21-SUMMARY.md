---
phase: 04-ingestion-pipeline
plan: 21
subsystem: testing
tags: [e2e, parse-formats, pdf, chunk-shape, embedding-batches, refusals]
requires:
  - phase: 04-14
    provides: parse flow, task-executor, roll-up, stack helpers in test/helpers/ingest.py
  - phase: 04-19
    provides: ingestion log routes (pages_total, pages_without_text, error)
  - phase: 04-20
    provides: page image route
provides:
  - test/testcases/test_parse_formats.py (16 cases)
  - test/testcases/test_parse_pdf.py (8 cases)
  - build_format_files, marker_word and chunk_texts helpers in test/helpers/ingest.py
affects: [04-22 and later e2e plans, 04-33 live tier]
tech-stack:
  added: []
  patterns: [one parsed dataset per module via a fixture, markers that are stand-alone plain words so the tokenised keyword filter finds them, poll with deadlines]
key-files:
  created:
    - test/testcases/test_parse_formats.py
    - test/testcases/test_parse_pdf.py
  modified:
    - test/helpers/ingest.py
key-decisions:
  - "No new decision rows: the plan adds tests only and settles nothing the docs leave open."
requirements-completed: []
duration: about 40 min
completed: 2026-10-17
---

# Phase 4 Plan 21: Format matrix and PDF journeys Summary

Eight formats (TXT, Markdown, CSV, JSON, HTML, DOCX, XLSX, PPTX) and the 13-page, partly blank, textless and damaged PDFs are now proven end to end on the real stack, with the loopback provider standing in only for the third-party embedding endpoint.

## What was proven

- Each format parses to chunks with the `naive` chunker; a marker word unique to the file is found by the chunk list `keywords` filter; the document counter equals the Elasticsearch count. HTML chunks contain no `<`, script or `alert` text (T-04-21-01). DOCX table cells, XLSX header row with a data value, and PPTX slide text plus notes are all in the chunks.
- Dataset `parser_config {chunk_token_num 64, delimiter "\n"}`: 30 lines of 20 tokens give chunks of at most 64 tokens, every line kept once and in order. Three 90 token lines give exactly six chunks (64 + 27, 64 + 27, 64 + 26), each line rebuilt from its two chunks with no loss or overlap. A document PATCH to `chunk_token_num 32` wins over the dataset (chunks at most 32).
- Per format, one stored chunk has `id`, `doc_id`, `kb_id`, `docnm_kwd` (file name), `content_with_weight`, `content_ltks`, `available_int 1`, `doc_enabled_int 1`, `origin_kwd parsed`, `task_id` of the document's task, `order_int` equal to the id suffix, `token_num_int > 0`, and a vector of the dataset dimension with L2 norm 1.0 within 1e-6.
- A 40-chunk document: every `/v1/embeddings` request carries at most 16 inputs.
- `.png` has `parseable false` and parse is 400 `parse_unavailable`; PATCH or PUT to `parser_id qa` is 400 `chunker_unavailable` with nothing changed; a document uploaded with `qa` is 400 at parse, stays `run 0`, and parses after PATCH to `naive`.
- 13-page PDF: no task rows after upload; exactly two task rows `(0, 12)` and `(12, 13)` read from the task table; manifests disjoint and their union equals the index; second task ids start `{doc_id}_12`, first task ids are below 1000; pages 1 to 13 all appear in positions; page 13 boxes lie inside the reported page size and the text contains "Page 13"; log and list row report `pages_total 13`, `pages_without_text 0`; JPEG thumbnail of at most 20000 characters; dataset `chunk_num` and `token_num` equal the index; polled progress is non-decreasing and ends at 1; a confirmed re-parse yields the same ids and count.
- 5-page PDF with pages 2 and 4 blank: finished, `pages_without_text 2`, `pages_total 5`, chunks on pages 1, 3, 5 only.
- All-blank PDF: `run 4` within 60 s, code `no_readable_text`, the D-14 sentence, task `retry_count 1`, log `attempts 1`, `retried false`, no internals in the JSON, no stale index rows, its page image still served, no pending stream entry for its task.
- Damaged PDF (valid `%PDF-` header, junk body): `file_damaged`, 3 of 3 attempts, `retried true`, no pending stream entries for its tasks (default 2 s and 4 s backoff, so the test needs no executor-test override and no stack restart).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test data] Marker must be a stand-alone token**
- **Found during:** Task 1 (first run, CSV)
- **Issue:** `markervalueX` is one token for the tokenised keyword filter, so searching `marker` found nothing. Not a product defect.
- **Fix:** CSV and XLSX values now carry the marker as its own word (`marker value`, `marker a`).
- **Files modified:** test/helpers/ingest.py
- **Commit:** 0c42b1d

**2. [Rule 1 - Test data] A damaged PDF must pass the upload content check**
- **Found during:** Task 2
- **Issue:** `garbage_bytes()` alone is refused at upload (400 `unsupported_type`, correct product behaviour), so it never reaches the parser.
- **Fix:** the test prepends `%PDF-1.4\n`; the type-sniffing refusal itself is already covered by upload tests.
- **Commit:** 6cb1312

**3. Housekeeping** In test/helpers/ingest.py three function-local `import json` lines were replaced by one module-level import (no behaviour change).

No product defects found. No product code changed, so the stack was not rebuilt.

## Verification

- `uv run python -m pytest -m e2e test/testcases/test_parse_formats.py test/testcases/test_parse_pdf.py test/testcases/test_parse_flow.py -q`: 39 passed in 68 s.
- `uv run python scripts/ci/run_all.py`: 7/7 gates passed (no `sleep(` in the new files).
- ruff check clean on the three touched files. The 04-19 flake did not recur.

## Known Stubs

None.

## Threat Flags

None. T-04-21-01 (HTML to chunk markup) and T-04-21-02 (internals in failure details) are asserted by the new tests.

## Self-Check: PASSED

- test/testcases/test_parse_formats.py, test/testcases/test_parse_pdf.py, test/helpers/ingest.py exist.
- Commits 0c42b1d and 6cb1312 exist.
