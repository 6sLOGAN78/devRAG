---
phase: 04-ingestion-pipeline
plan: 15
subsystem: ingestion
tags: [parser-config, document-list, document-detail, pdf-page-count, pydantic, mysql]
requires:
  - phase: 04-06
    provides: rag.parsers.router.parseable
  - phase: 04-08
    provides: pdf.count_pages
  - phase: 04-12
    provides: worker log rows (pipeline_operation_log.dsl with error, pages_total, pages_without_text)
provides:
  - api/db/services/parser_config.py (ParserConfig, validate_parser_config, require_buildable)
  - api/db/services/document_view.py (ROW_KEYS, row_dto, list_rows, document_detail)
  - api/db/services/pdf_pages.py (pdf_page_count, clear_cache)
  - document_service.list_rows_view
affects: [04-16 routes, SPA document table and detail]
tech-stack:
  added: []
  patterns: [typed config model with extra=allow, caller-supplied structural error factory, SQL-side thumbnail length guard, RIGHT() tail read of progress_msg]
key-files:
  created:
    - api/db/services/parser_config.py
    - api/db/services/document_view.py
    - api/db/services/pdf_pages.py
    - test/unit_test/test_parser_config.py
    - test/integration/test_document_view.py
  modified:
    - api/db/services/knowledgebase_service.py
    - api/db/services/document_service.py
    - test/integration/test_dataset_lifecycle.py
    - test/integration/test_document_service.py
key-decisions:
  - "validate_parser_config takes a `structural` error factory: shape problems (not an object, not JSON, over 4096 characters) keep each caller's existing reason (dataset_invalid on datasets, parser_invalid on the upload override), while a bad known value or too-deep nesting is parser_config_invalid with data.field. This keeps every Phase 3 assertion unchanged."
  - "validate_parser_config returns only the keys that were sent (exclude_unset), so defaults are still merged by the callers as before."
  - "Row key `chunk_count` replaces Phase 3 `chunk_num` in the new row set; the upload response and Phase 3 list_view keep document_dto."
  - "progress_message is read for run 1 and run 4 rows (running and failed), as the last 2,000 characters via SQL RIGHT(), then last non-empty line, redacted, cut to 300."
  - "error.message always comes from PLAIN_MESSAGES by the typed code; step and code are checked against STEPS and FAILURE_CODES, else parse/unexpected. Stored detail text never reaches the row."
  - "Thumbnail length is guarded in SQL (NULL above 20000 characters) so large values are not transferred, then the prefix is checked in Python."
  - "pdf_page_count takes settings plus an optional storage argument; document_detail likewise, so tests can pass a counting wrapper."
requirements-completed: []
duration: ~45min
completed: 2026-10-17
---

# Phase 4 Plan 15: Parser config validation, list rows, detail and PDF page count

Parser settings are typed and bounded wherever they are written, and the document list and detail services now carry the Phase 4 facts (state, progress line, failure, thumbnail, page counts) at four SQL statements per page and no doc-store call. Services only; routes arrive in 04-16.

## Tasks

| Task | Commits | Result |
|------|---------|--------|
| 1 ParserConfig validation | RED 0ab32c2, GREEN 254c7c3 | 24 unit cases; 5 new integration cases in test_dataset_lifecycle |
| 2 List rows, detail, page count | RED afc62de, GREEN 504099c | 15 new integration cases in test_document_view plus one in test_document_service |

## Verification

- `test/unit_test/test_parser_config.py`: 24 passed (failed at import before the module existed). Full unit suite: 1962 passed, 3 skipped.
- Integration: test_document_view, test_document_service, test_knowledgebase_service, test_ingestion_service, test_upload_service, test_dataset_lifecycle (parser cases): all pass. Phase 3 assertions on `dataset_invalid` and `parser_invalid` unchanged.
- `scripts/ci/run_all.py`: 7/7 gates. No `re.compile` in parser_config.py; `RecursionError` is caught there. `location` and `content_hash` appear in document_view.py only in the detail select and page-count call, never in ROW_KEYS.
- Statement count test: 20-row page issues at most 4 SELECTs with `get_doc_store` patched to raise.
- The HTTP error mapper already merges `ServiceError.data` into the envelope, so `data.field` reaches the client with no handler change (dataset_api.py untouched).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Reason codes for structural parser_config errors**
- **Found during:** Task 1
- **Issue:** the plan says a payload over the cap "keeps its existing refusal", but existing tests (kept unchanged) require `dataset_invalid` for datasets and `parser_invalid` for the upload override.
- **Fix:** the `structural` factory argument described above.
- **Commit:** 254c7c3

**2. [Rule 1 - Bug] Statement-count test counted the visibility lookup**
- **Found during:** Task 2
- **Issue:** the first version resolved the visible dataset inside the counted region (5 SELECTs).
- **Fix:** resolve it before patching; the service itself uses 4.
- **Commit:** 504099c

### Other notes

- `DTO_KEYS` in test_document_service.py is unchanged: the Phase 3 `list_view` and upload still use `document_dto`, as the plan's hard constraints require. A new test pins `list_rows_view` to `ROW_KEYS`, and also asserts the Phase 3 list is still on `DTO_KEYS`.
- A `ruff --fix` run touched three unrelated test files; they were restored with `git checkout` before committing.
- Plan 04-16 should switch the list handler to `list_rows_view`, change the e2e pins and the leak sweep's `thumbnail` ban, and run the page-count in the storage executor with a timeout.

## Decisions needing rows

No Phase 3 test was changed or weakened. Rows to add to DECISIONS.md for the items above: structural-vs-field reason split (R-?), `chunk_count` naming in the row set, progress message read for failed rows as well as running ones.

## Known Stubs

None.

## Threat Flags

None. T-04-15-01..05 mitigations applied and tested: ranges and types, 1,200-level nesting test, explicit ROW_KEYS with typed error text, thumbnail prefix and length limit, per-(doc, hash) page-count cache.

## Self-Check: PASSED

Files exist; commits 0ab32c2, 254c7c3, afc62de, 504099c present.
