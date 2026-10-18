---
phase: 04-ingestion-pipeline
plan: 28
subsystem: web
tags: [react, sheet, parsing-details, parsing-log, lazy-route, failure-copy, i18n]
requires:
  - phase: 04-26
    provides: row Details link and menu item, useParseActions, files test-server area
  - phase: 04-25
    provides: polling hooks, failure code maps, useDatasetBinding
  - phase: 04-24
    provides: ingestion services, DATASET_LOGS_ROUTE and datasetLogsPath
provides:
  - "ParsingDetailsSheet: right-hand Dialog sheet with status, fixed-copy reason, retry line, fields, provider message and progress log"
  - "Parsing log page at /dataset/logs (lazy route, no nav entry)"
  - "StatusKindBadge shared by table, sheet and log; FAILURE_CODES and STEPS exports"
  - "test-server area ingestion-logs.ts and locale area details (en, zh draft)"
affects: [04-29, 04-30, 04-32]
tech-stack:
  added: []
  patterns: [sheet body keyed by entry, close-then-act via unmount watcher, owner-supplied permission callback]
key-files:
  created:
    - web/src/pages/dataset/parsing-details-sheet.tsx
    - web/src/pages/dataset/parsing-details-sheet.test.tsx
    - web/src/pages/dataset/logs/index.tsx
    - web/src/pages/dataset/logs/logs.test.tsx
    - web/src/test/server-areas/ingestion-logs.ts
    - web/src/locales/areas/en/details.json
    - web/src/locales/areas/zh/details.json
  modified:
    - web/src/pages/dataset/dataset-files.tsx
    - web/src/pages/dataset/document-row.tsx
    - web/src/pages/dataset/document-row-actions.tsx
    - web/src/pages/dataset/document-status-badge.tsx
    - web/src/constants/routes.ts
    - web/src/constants/failure-codes.ts
    - web/src/services/ingestion-service.ts
    - web/src/services/document-service.ts
    - web/src/test/server-areas/files.ts
    - web/src/layouts/layouts.test.tsx
    - web/src/routes.test.tsx
    - .planning/DECISIONS.md
key-decisions:
  - "R-183: DatasetFiles owns the sheet; Parse again fires only after the sheet unmounted; failure messages keep 301 characters so over-long ones are detectable"
requirements-completed: []
duration: ~1h
completed: 2026-10-19
---

# Phase 4 Plan 28: Parsing details sheet and parsing log page Summary

A failed or partly indexed document now explains itself in a right-hand sheet (fixed-copy reason, retry line, failed step, attempts, timing, chunks, pages without text, provider message, progress log), and every run of a dataset is browsable on a lazy `/dataset/logs` page, 20 a page, newest first.

## Tasks

1. **ParsingDetailsSheet and entry points** (RED ac406f6, GREEN b20537c). The sheet body is mounted only while open and keyed by the log id (FE-04). Everything renders as text nodes. Known codes map to fixed copy, unknown codes show the server message only for 1 to 300 characters. The log box follows new lines only when the reader is at the bottom; the entry polls every 2 s while it runs. 'Parse again' closes the sheet and the request goes out only after the content has unmounted (R-152). Entry points: the row 'Details' link and the 'Parsing details' menu item, with focus returning to the opener.
2. **Parsing log page and route** (RED c6883e5, GREEN a7a12a4). Table with document, started, duration, result badge (icon and text, short reason on failures), attempts and a Details button that opens the same sheet; pagination named 'Parsing log pages'; loading, empty, error, dataset-not-found and page-beyond-the-last states; binds the workspace through `useDatasetBinding` and sends nothing before `bound`. Registered with `DATASET_LOGS_ROUTE`, no `nav`; Datasets stays highlighted through the existing `/dataset/` prefix match.

## Verification

- `npx vitest run --project unit`: 71 files, 1419 tests pass (sheet suite 55 tests, logs page 16; `src/pages/dataset`, layouts, routes, locales, constants all green).
- `npx tsc --noEmit` exits 0; `npm run build` exits 0 and `scripts/check-chunks.mjs` reports 35 lazy chunks; `git diff --stat -- web/package.json web/package-lock.json` is empty; no `dangerouslySetInnerHTML` or `iframe` under `web/src/pages/dataset`.
- `uv run python scripts/ci/run_all.py`: 7/7 gates pass (decisions: 183 rows).
- The live-stack vitest project was not run; this plan verifies the unit scope.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Over-long failure messages were shown cut.** `toError` in `ingestion-service.ts` and `document-service.ts` sliced the message to 300 characters, so a 400-character message for an unknown code passed the "1 to 300 characters" rule and showed truncated (T-04-28-02, D-08). Both mappers now keep 301 characters, so the rule rejects it and the unexpected-reason sentence shows. Found by the sheet test. Commit b20537c.

**2. [Rule 3 - Blocking] `FAILURE_CODES` and `STEPS` did not exist.** The plan's acceptance criteria iterate them, but `failure-codes.ts` kept the tables private. Both are now exported from the existing tables. Commit ac406f6.

### Other differences

- **Sheet ownership.** The plan wires the sheet in `dataset-files.tsx`; the 04-26 handoff said `DatasetWorkspace` passes `onShowDetails`. `DatasetFiles` owns the sheet and the optional `onShowDetails` prop is gone, so `DatasetWorkspace` is unchanged. `onShowDetails` now also receives the opener element.
- **Files outside the plan's list:** `document-status-badge.tsx` (exports `StatusKindBadge`, used by the sheet and log), `files.ts` (`addFileLog`, `fileExtraOf` for the new area), `failure-codes.ts`, the two service mappers, row R-183 in `DECISIONS.md`.
- **Parse again on the log page.** The log page has no document list, so it passes no `canParseAgain` and the button is absent there; the dataset page shows it for the document's latest failed or cancelled run when the caller may change it.
- **Extra locale keys:** `datasets.details.loading`, `datasets.ingestion.log.loading` and `datasets.ingestion.log.documentTitleFallback` (screen-reader loading text and a title before the dataset loads).
- **TDD:** RED commits ac406f6 and c6883e5 fail on the missing modules; the scroll-follow and polling tests use real timers through `waitUntil`.

## Known Stubs

None.

## Threat Flags

None. Log lines, provider messages, file names and reasons render as text nodes (hostile-line tests assert no element is created); logs and entry requests wait for the workspace binding; `id` is checked by the binding hook and `page` is clamped.

## Notes for later plans

- Chinese strings in `details.json` are drafts for the B-18 review.
- The chunk inspector's failed state (04-30) can reuse `ParsingDetailsSheet` (`datasetId`, `logId`, `open`, `onOpenChange`, `onCloseAutoFocus`, optional `canParseAgain` and `onParseAgain`) and `useReasonText`.
- Route-link coverage for `chunkPath` and `documentViewerPath` belongs to 04-32; `routes.test.tsx` now has the matching case for `datasetLogsPath`.

## Self-Check: PASSED

- Commits ac406f6, b20537c, c6883e5 and a7a12a4 exist; all created files exist; full unit suite, build and the 7 CI gates are green.
