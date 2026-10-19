---
status: partial
phase: 04-ingestion-pipeline
source: [04-35-PLAN.md, 04-VALIDATION.md]
started: 2026-10-19
updated: 2026-10-19
---

## Current Test

[awaiting human testing]

## Tests

### 1. Box alignment on the chunk inspector page image (UI-16)
expected: Open the chunk inspector of the 13-page PDF. On page 1 and on page 13 the highlighted rectangle sits on the text of the selected chunk. Tests only prove the box lies inside the image and that the page is right. Known limit (R-190): chunks cut from one text block share the block's rectangle, so two neighbouring chunks may show the same box.
evidence: scratch screenshots from plan 04-34, outside the repository: `/tmp/claude-1000/-home-logan78-desktop-x-devRAG/1461d27c-08a3-4546-814c-4d7b2106862b/scratchpad/shots/devrag-inspector-box-page1.png` and `devrag-inspector-box-page13.png` (regenerate with `uv run python -m pytest -m e2e test/testcases/test_spa_ingestion_browser.py -q` if they are gone).
result: [pending]

### 2. Chinese draft copy review (B-18, B-35)
expected: A Chinese reader confirms that every file under `web/src/locales/areas/zh/` added in Phase 4 reads correctly: chunking, details, editor, failures, inspector, parsing and viewer.
result: [pending]

### 3. PDF page cap (B-34)
expected: The user confirms 20,000 pages as the PDF cap or names another number (R-189).
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
