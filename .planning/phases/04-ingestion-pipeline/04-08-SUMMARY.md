---
phase: 04-ingestion-pipeline
plan: 08
subsystem: ingestion
tags: [pdf, pypdfium2, rasterize, thumbnail]
requires:
  - phase: 04-06
    provides: parser contract (ParsedBlock, PageBox, ParseReport, SourceFile), router with lazy pdf loader
provides:
  - rag/parsers/pdf.py (count_pages, parse, rasterize_page, thumbnail_data_url, PDFIUM_LOCK)
  - test/helpers/pdf_files.py (text_pdf, thirteen_page_pdf, garbage_bytes, truncated)
affects: [04-14, 04-21, 04-33, worker pipeline]
tech-stack:
  added: []
  patterns: [process-wide pdfium RLock, per-page generator, fixed-message typed errors]
key-files:
  created:
    - rag/parsers/pdf.py
    - test/helpers/pdf_files.py
    - test/unit_test/test_pdf_parser.py
  modified: []
key-decisions:
  - "pdfium text-rect coordinates are unrotated user space; boxes are mapped through crop-box origin then rotation (0/90/180/270) to the displayed page, and verified against rendered pixels"
  - "Each page is opened from a fresh PdfDocument inside the lock and closed in finally, so no pdfium object lives across generator yields"
requirements-completed: []
duration: ~25min
completed: 2026-10-17
---

# Phase 4 Plan 08: PDF parser, rasteriser, thumbnail, PDF generator

Text-layer PDF parsing on pypdfium2 alone, with boxes in top-left PDF points aligned to the rendered page (rotation and crop box), a zoom-3 rasteriser, a thumbnail data URL under 16384 characters and a hand-written PDF byte generator for tests.

## Tasks

1. PDF generator helper - commit 1b6695c
2. pdfium parser, rasteriser, thumbnail (and the suite) - commit 372d01b

## Verification

- `test_pdf_parser.py` and `test_parser_router.py`: 27 passed. Alignment holds for rotation 0, 90, 180, 270 and an offset crop box (box region has ink, shifted empty region has none).
- `scripts/ci/run_all.py`: 7/7 gates passed. No `pdfplumber`/`fitz`/`pymupdf` under `rag`. `PDFIUM_LOCK` appears 4 times, `finally` 8 times.
- Installed pypdfium2 5.13.0 API used.

## Deviations from Plan

- Process: the generator helper was committed first, but the parser was written before the test file existed, so there is no separate red-suite run or recorded import-error line. Tests and parser were then committed together (the same pattern as 04-06).
- Test geometry: the offset crop box used is (50, 200, 500, 842) rather than a box that excludes the text line at y=770; the plan did not fix the values. Rotation 180 and 270 were added to the alignment cases.
- The plan's "same-sized region shifted down" check falls back to shifting up when the shifted region would leave the page (rotated cases).

## Known Stubs

None.

## Threat Flags

None. Mitigations T-04-08-01..05 applied: 1,000,000 page cap, per-range opening, one process lock plus two-thread test, fixed error messages (test asserts no path), per-page generator closing objects in finally.

## Self-Check: PASSED
- Files exist; commits 1b6695c and 372d01b present.
