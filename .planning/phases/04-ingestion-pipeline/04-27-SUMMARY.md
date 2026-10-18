---
phase: 04-ingestion-pipeline
plan: 27
subsystem: web
tags: [vitest, live, parse, dataset-page, polling]
requires:
  - phase: 04-26
    provides: parse controls, status badge, progress cell, ingestion summary
provides:
  - "parse.live.test.ts: real-stack journey from Not started to Finished with 3 chunks and no reload"
  - "textFile(paragraphs, name) builder in web/src/test/live/documents.ts"
affects: [04-34]
key-files:
  created:
    - web/src/pages/dataset/parse.live.test.ts
    - web/src/test/live/documents.ts
key-decisions: []
requirements-completed: []
duration: ~25min
completed: 2026-10-19
---

# Phase 4 Plan 27: Live parse journey for the dataset page Summary

One live vitest journey proves the real dataset page, HTTP client, API, Redis queue and executor container take an uploaded TXT from Not started to Finished (`3 chunks`, 100%, summary Finished 1 / Chunks 3, meta line 3 chunks) with no reload.

## Task 1 (commit 200ea89)

- `textFile(3, "notes.txt")`: three paragraphs of a marker word plus 300 `the`, which cannot merge under the 512-token budget, so exactly 3 chunks.
- The journey registers its own account, saves the Node loopback provider through the real service, creates a dataset with the fake embedding model, uploads through the real service, renders the real `/dataset/files?id=` route, presses `Parse notes.txt`, and waits (120 s bound, `waitUntil`) for `data-run` 3.
- No-reload proof: a marker attribute on the `dataset-page` node survives and the same node is still mounted; at least two document-list GETs were recorded by an interceptor on the application's own axios instance after the press (polling). Every `aria-valuenow` seen while running is at most 99; no toast on success; the loopback provider received `/v1/embeddings`.
- Cleanup: dataset deleted by recorded id and tenant; the account is removed by the runner from `LIVE_ACCOUNTS_FILE`.

## Verification

- Live file against the rebuilt stack: 1 passed (about 9 s).
- Red run with the executor container stopped: fails with `waitUntil timed out after 120000ms waiting for the row to reach Finished (data-run 3)`. Executor restarted afterwards.
- `npx vitest run --project unit`: 69 files, 1346 tests pass. `npx tsc --noEmit` exits 0. `scripts/ci/run_all.py`: 7/7 gates pass. `git diff --stat` on `web/package.json` and the lockfile is empty. No `setTimeout(`/`sleep(` in the two files.

## Deviations from Plan

None in behaviour. Note: the acceptance grep `grep -rn OPENROUTER web/src` is not empty, but every hit is pre-existing and none is a key: test seed constants in `provider-dialogs.test.tsx` and the env-variable name in `web/src/test/live/provider-key.ts`. The new files contain no such text and no key reaches the browser tier.

## Bugs found

None. The screen and the stack agreed on the first run.

## Known Stubs

None.

## Threat Flags

None.

## Self-Check: PASSED

- Both created files exist; commit 200ea89 exists.
