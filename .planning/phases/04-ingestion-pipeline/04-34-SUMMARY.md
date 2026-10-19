---
phase: 04-ingestion-pipeline
plan: 34
subsystem: testing
tags: [vitest-live, real-chrome, cdp, ingestion, inspector, e2e]
requires:
  - phase: 04-27
    provides: textFile builder, first live parse journey
  - phase: 04-32
    provides: document viewer, download hook
  - phase: 04-33
    provides: ingest helpers, 13-page PDF chunk configuration
provides:
  - "ingestion.live.test.ts: six dataset-page journeys on the real stack"
  - "inspector.live.test.ts: four inspector journeys on the real stack"
  - "test_spa_ingestion_browser.py: six real-Chrome journeys"
  - "TS PDF, blank PDF and damaged DOCX builders; a delaying and refusing loopback provider; ingest-world helper"
affects: [04-35]
tech-stack:
  added: []
  patterns: [jsdom object-URL registry so blob bytes can be read, press helper that ignores infinite spinner animations]
key-files:
  created:
    - web/src/pages/dataset/ingestion.live.test.ts
    - web/src/pages/chunk/inspector.live.test.ts
    - web/src/test/live/ingest-world.ts
    - test/testcases/test_spa_ingestion_browser.py
  modified:
    - web/src/test/live/documents.ts
    - web/src/test/live/fake-provider.ts
    - test/helpers/chrome_cdp.py
key-decisions:
  - "No new decision row: only test tiers were added"
requirements-completed: []
duration: ~2h (with an interruption)
completed: 2026-10-19
---

# Phase 4 Plan 34: Live and real-browser journeys Summary

The Phase 4 screens now pass against the rebuilt stack and the real executor container in the vitest live project (10 tests) and in a real headless Chrome (6 journeys); only the third-party provider is a loopback fake.

## Tasks

1. **Vitest live journeys** (b489958). Stack rebuilt first (compose `up -d --build`, `wait_stack.sh`). Dataset page: 13-page PDF Not started to Parsing to Finished with 26 chunks and no reload (bar never above 99, non-decreasing); Parse again dialog with 26 / 0 / 0 and the same count after confirming (checked by a new log id); poison DOCX Failed with the damaged-file sentence, step "Reading the file", "Stopped after 3 attempts.", clean log; blank PDF fails at once with the D-14 sentence and "Not retried..."; cancel of a 200-chunk TXT shows Cancelled or Partly indexed, Parse again starts with no dialog; a team member sees status and chunks and no parse, select, switch, delete or change-menu items. Inspector: page image bytes behind the `blob:` source, box percentages inside the image wrapper, page 13 chunk changes the image and the caption; edit, add and switch-off survive a fresh mount and the Off filter lists the chunk; a refused save keeps the text and shows the refusal; Parse again states 4 / 1 / 1.
2. **Real Chrome journeys** (9f56939). Parse press to Finished with a MutationObserver record Not started, Parsing, Finished and an unchanged `performance.timeOrigin`; inspector image 1785 px wide, box inside the image (1 px tolerance) on page 1 and page 13 and the image changes; edit, add, switch off survive a reload and the Off filter; Parse again dialog 4 / 1 / 1 and Replace brings back 3 chunks; cancel then Parse again with no dialog; viewer PDF page image, TXT in a `<pre>`, DOCX download saved byte for byte as report.docx.

## Verification

- `npx vitest run --project live` on both files: 10 of 10, three consecutive full passes of the dataset file.
- `uv run python -m pytest -m e2e test/testcases/test_spa_ingestion_browser.py -q`: 6 passed.
- `--project unit`: 81 files, 1691 tests; `npx tsc --noEmit` clean; `uv run python scripts/ci/run_all.py`: 7 of 7 gates.
- No `setTimeout(` or `sleep(` in the new tests; the provider's delay uses `node:timers/promises`. `git diff --stat -- web/package.json web/package-lock.json` empty.
- Inspector screenshots for the manual box check (outside the repository): `/tmp/claude-1000/-home-logan78-desktop-x-devRAG/1461d27c-08a3-4546-814c-4d7b2106862b/scratchpad/shots/devrag-inspector-box-page1.png` and `devrag-inspector-box-page13.png`. Default location when `DEVRAG_SCREENSHOT_DIR` is unset is the system temp directory.

## Deviations from Plan

- **[Rule 3] Shared helper added.** `web/src/test/live/ingest-world.ts` is not in the plan's file list; it holds accounts, workspace, dataset, mounting and cleanup for both live files.
- **jsdom limits.** jsdom decodes no images and lays out no boxes, so the vitest tier checks the PNG header behind the `blob:` address (a registry shim for `URL.createObjectURL`, installed by the test) and the box percentages. Pixel geometry is asserted in real Chrome.
- **Cancel scenario size.** The default executor indexes 64 chunks per batch, so a 40-chunk document is indexed in one step. The cancel journeys use 200 paragraphs and a 1.5 s provider delay. The default executor was not reconfigured.
- **Press helper.** `_press_expr` waits only for finite animations; a running spinner never settles and blocked the cancel press.
- **Viewer image test id.** A PDF page in the viewer uses `preview-image` (PagePreview), not `viewer-image`.
- The plan's acceptance `grep -rn OPENROUTER web/src` is not empty: it matches the existing `web/src/test/live/provider-key.ts` (03-26, reads the key server-side for the model tier) and a seed name in a unit test. The new files contain none.
- No Chinese or requirement changes; requirements not ticked.

## Bugs found

None fixed. Observation, not fixed (outside this plan): PDF chunks cut from one text block all carry that block's whole box, so chunk 25 (page 13 lines 1 to 3) and chunk 26 (lines 4 to 6) are drawn with the same rectangle covering all six lines (positions come from the parser's block, not from the chunk's lines). The box is inside the page and the page is right; the highlight is coarser than the chunk. Candidate for a later phase.

## Known Stubs

None.

## Threat Flags

None. The real provider key never enters the browser tier; failure details are asserted against a trace, path and key pattern; cleanup is by recorded dataset id and account file.

## Self-Check: PASSED

- Commits b489958 and 9f56939 exist; all created files exist; both live files, the Chrome file, the unit suite, tsc and the 7 gates pass.
