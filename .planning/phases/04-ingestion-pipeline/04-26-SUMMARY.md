---
phase: 04-ingestion-pipeline
plan: 26
subsystem: web
tags: [react, polling, parse-controls, status-map, selection, reparse-dialog, ingestion-summary, i18n]
requires:
  - phase: 04-25
    provides: polling hooks, onSettled mutations, failure placement, failures locale area
  - phase: 04-24
    provides: Phase 4 services and path builders
  - phase: 04-05
    provides: Switch, Checkbox, canChangeDocument
provides:
  - "DocumentStatusBadge: full status map (icon and text per state, detail lines, Unknown fallback)"
  - "DocumentProgress: floored percentage capped at 99 while running, latest server line, bar"
  - "DocumentRowActions, SelectionBar, ReparseDialog, useParseActions, useParseAnnouncements"
  - "IngestionSummary card, paused-updates notice, polite live region, chunk count in the meta line"
  - "test-server area files.ts and parsing locale area (en, zh draft)"
affects: [04-27, 04-28, 04-29, 04-30, 04-32]
tech-stack:
  added: []
  patterns: [server-decided confirmation, dialog body keyed by opening, key-returning failure placement, area handler with advanceParse]
key-files:
  created:
    - web/src/pages/dataset/document-progress.tsx
    - web/src/pages/dataset/document-row-actions.tsx
    - web/src/pages/dataset/selection-bar.tsx
    - web/src/pages/dataset/reparse-dialog.tsx
    - web/src/pages/dataset/parse-actions.ts
    - web/src/pages/dataset/ingestion-summary.tsx
    - web/src/pages/dataset/parse-controls.test.tsx
    - web/src/pages/dataset/reparse-dialog.test.tsx
    - web/src/pages/dataset/ingestion-summary.test.tsx
    - web/src/test/server-areas/files.ts
    - web/src/test/files-harness.tsx
    - web/src/locales/areas/en/parsing.json
    - web/src/locales/areas/zh/parsing.json
  modified:
    - web/src/pages/dataset/document-status-badge.tsx
    - web/src/pages/dataset/document-row.tsx
    - web/src/pages/dataset/dataset-files.tsx
    - web/src/pages/dataset/dataset-workspace.tsx
    - web/src/pages/dataset/dataset-files.test.tsx
    - web/src/pages/dataset/dataset-workspace.test.tsx
    - .planning/DECISIONS.md
key-decisions:
  - "R-181: inSearch key names, Link needs a router, error state only before the first load, files.ts area"
requirements-completed: []
duration: ~1h15min
completed: 2026-10-19
---

# Phase 4 Plan 26: Parse controls and live status on the dataset page Summary

The dataset page now lets members who may change a document parse, cancel, re-parse behind a server-decided confirmation, switch search and act on a selection, while everyone sees the true status, a progress line that updates every 2 seconds in place, an ingestion summary card and an honest "updates paused" notice.

## Tasks

1. Status map, progress cell, thumbnail, row and columns: table-driven `DocumentStatusBadge` (eight states with icon and text, skipped-pages line, failure sentence from `failureSentence`, spinner off under reduced motion), `DocumentProgress` (`floor`, cap 99 while running, em dash with sr-only text when failed), `DocumentRow` with thumbnail fallback, name link built with `chunkPath`, `data-run` and `data-doc-id`, search switch or read-only text, select cell. Committed with task 2 as b6b4b4d.
2. Row actions, selection bar, search switch and the Parse again dialog: `useParseActions` owns in-flight guards, the pending confirmation and error placement; `ReparseDialog` keeps its error, counts and busy state in a body keyed by the opening (FE-04), blocks Escape and dismissal while the replace is in flight and returns focus to the row's menu button. b6b4b4d.
3. Ingestion summary, paused notice, announcements, meta line: `IngestionSummary` (own query, own error line, skeletons, zeros shown, "Parsing log" link via `datasetLogsPath`), `usePollHealth` notice, `useParseAnnouncements` region without percentages, `dataset.meta.chunks` in the meta line. Implementation in b6b4b4d, tests in e4e68c3.

## Verification

- `npx vitest run --project unit`: 69 files, 1346 tests pass (parse controls 29, reparse dialog 10, summary 7, files 41, workspace 37, locale parity and copy scan green).
- `npx tsc --noEmit` exits 0; `git diff --stat -- web/package.json web/package-lock.json` is empty; no `dangerouslySetInnerHTML` under `web/src/pages/dataset`.
- `scripts/ci/check_decisions.py`: 181 rows OK.
- The live-stack vitest project and `npm run build` were not run (the stack was being restarted and the plan verifies the unit scope only).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Locale key collision.** The UI-SPEC key `datasets.files.search.on/off/label` collides with the existing string `datasets.files.search` (R-151 rule 4, duplicate keys are a load error). The switch copy lives under `datasets.files.inSearch.{on,off,label}`. Recorded in R-181.

**2. [Rule 3 - Blocking] Router above the table.** The name link and the menu links use `Link`, so the table needs a router; the existing table tests got a `MemoryRouter`. Existing Phase 3 expectations changed only where the new design requires it: the header list (select and In search columns), the "Unknown status" test (run "1" is now Parsing, so it uses an unknown value), the badge test (the badge takes a document view) and the member row test (members now have the menu button).

**3. [Rule 1 - Bug] Poll failure replaced the table.** `documents.isError` swapped the table for the error state on a failed poll. The error state now shows only when no list has loaded, which the paused notice requires ("rows keep their last values").

**4. [Rule 3] Copy scan.** Generic type shapes such as `=> Promise<void>` and a `"documents"` type literal tripped the hard-coded-copy scan; the interfaces use method signatures and the `ConfirmCount` type.

**5. Extra files.** `web/src/test/files-harness.tsx` (shared harness for the two new suites) and `PendingConfirm.session` (keys the dialog body by opening) are not in the plan's file list.

### Process

- **TDD order:** the implementation was written before the tests were run, so the tests passed on first run and there is no separate RED commit. Tests were then written against the stated behaviours (including the FE-04 case, the Escape-in-flight case and the 0.996 case). Tasks 1 and 2 share one commit because `dataset-files.tsx` wires both; task 3's tests are a separate commit.
- The `Details` link and the "Parsing details" menu item render only when `onShowDetails` is passed to `DatasetFiles` (plan 04-28 supplies it); `DatasetWorkspace` does not pass it yet.
- Not built here by design: "Chunking method" menu item and "Default chunking method" (04-29).

## Notes for later plans

- `DatasetFiles` takes an optional `onShowDetails(logId)`; wire it in 04-28.
- Chinese strings in `parsing.json` are drafts for the B-18 review.
- The row-link test that each target matches a registered route belongs to plan 04-32; here each `href` is asserted equal to the helper output.

## Known Stubs

None.

## Threat Flags

None. File names, progress lines, reasons and thumbnails render as text nodes or from the validated `thumbnail` field (decode failure falls back to the icon); controls are drawn by `useCanChangeDocument` and the server stays authoritative (403 shows the lost-permission copy and refetches).

## Self-Check: PASSED

- Commits b6b4b4d and e4e68c3 exist; created files listed above exist; full unit suite green.
