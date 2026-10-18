---
phase: 04-ingestion-pipeline
plan: 30
subsystem: web
tags: [react, chunk-inspector, page-preview, bounding-boxes, react-query, i18n]
requires:
  - phase: 04-29
    provides: chunking dialog, files test-server area
  - phase: 04-28
    provides: ParsingDetailsSheet owner pattern, useDatasetBinding page shape
  - phase: 04-26
    provides: useParseActions, ReparseDialog, document detail hooks
  - phase: 04-24
    provides: CHUNK_ROUTE, chunkPath, documentViewerPath
  - phase: 04-20
    provides: fetchPageImage (blob, JPEG/PNG only)
provides:
  - "PagePreview: page navigation, four zoom levels, percent-positioned box overlay, away and no-place notes"
  - "boxStyle (percent geometry), usePageImage (blob to object URL, revoked on change)"
  - "Chunk inspector page at /chunk?id=&doc= with list, search, filter, paging, per-chunk switch, notices and every state"
  - "Test-server area chunks.ts (list, switch PATCH, page image) with an exported chunk store for 04-31"
affects: [04-31, 04-32]
tech-stack:
  added: []
  patterns: [percent-of-page overlay, object URL exposed only for the blob it was made for, focus plan kept until the refetch removes the chunk]
key-files:
  created:
    - web/src/components/document-preview/box-geometry.ts
    - web/src/components/document-preview/use-page-image.ts
    - web/src/components/document-preview/page-preview.tsx
    - web/src/components/document-preview/page-preview.test.tsx
    - web/src/pages/chunk/index.tsx
    - web/src/pages/chunk/chunk-card.tsx
    - web/src/pages/chunk/chunk-list.tsx
    - web/src/pages/chunk/chunk-notices.tsx
    - web/src/pages/chunk/inspector-states.tsx
    - web/src/pages/chunk/chunk-list.test.tsx
    - web/src/pages/chunk/chunk-states.test.tsx
    - web/src/pages/chunk/chunk-inspector.test.tsx
    - web/src/test/server-areas/chunks.ts
    - web/src/locales/areas/en/inspector.json
    - web/src/locales/areas/zh/inspector.json
  modified:
    - web/src/constants/routes.ts
    - web/src/components/page-header.tsx
    - web/src/components/ui/segmented-control.tsx
    - web/src/layouts/layouts.test.tsx
    - web/src/routes.test.tsx
    - web/src/test/server-areas/files.ts
    - .planning/DECISIONS.md
key-decisions:
  - "R-185: request order binding, document detail, chunk list; boxes in percent of the page clipped to it; page sizes snapshotted with the selected chunk; usePageImage is the only object-URL site; focus plan kept until the refetch removes the chunk"
requirements-completed: []
duration: ~1h30
completed: 2026-10-19
---

# Phase 4 Plan 30: Chunk inspector Summary

Members can open `/chunk?id=&doc=` and read a document's chunks beside its original pages: the selected chunk's bounding boxes are drawn in percent of the page over a server-rendered image, so zoom and window size never misalign them, and the list searches, filters All/On/Off, pages 20 at a time and switches single chunks on and off.

## Tasks

1. **Box geometry, page image hook, PagePreview** (RED 6f90015, GREEN 39cea60). `boxStyle` clips a position to the page and returns percent strings, or null for a non-finite number, an empty or off-page box, or a missing page size. `usePageImage` fetches a blob through the HTTP client, makes the object URL in an effect, hands it out only for the blob it was made for, and revokes it on page, document or unmount (`staleTime: Infinity`, `gcTime: 60000`). `PagePreview` has the page nav (aria-disabled ends, polite caption), zoom 100/150/200/300 and Fit width, a focusable scroll container, a wrapper with the page's aspect ratio, `aria-hidden` inert boxes with a 4 by 4 px minimum, the skeleton and the retry state, the "away" note with Go to page, the "no place" note and an sr-only announcement; the first box is scrolled into view on selection (`auto` under reduced motion).
2. **List, cards, switch, notices, states** (RED d633f2a, GREEN 2ee145e). `ChunkCard` (header button with `aria-pressed`, page chips for PDF only, Edited / Added by hand / Off badges, text node, 2 px accent bar, dimmed dashed Off card, On/Off switch), `ChunkList` (300 ms debounced search, segmented filter, `<ol>`, pager named "Chunk pages", arrow/Home/End keys, non-optimistic switch with `aria-busy`, announcement and focus plan under the On/Off filters), `ChunkNotices`, and the states (skeleton, never parsed, no parser, parsing with progress, failed, cancelled, no match, none off, list error, not found, no-preview note).
3. **Page, binding, route** (RED 3e240af, GREEN 0a7a07f). Validates `id` and `doc` before any request, clamps `page`, cuts `keywords` to 100, normalises `show`; requests in order binding, document detail, chunk list (FE-02: one chunk request for the dataset's workspace with `page=2&keywords=x` intact); polls the detail while parsing and refetches the list on a changed count and once when parsing ends; two columns from 1024 px with the sticky pane, or the `max-w-3xl` column with the one-line note; parse, cancel and re-parse confirmation reuse `useParseActions` and `ReparseDialog`; the details sheet opens from the partly-indexed notice and the failed state. `/chunk` is registered with `CHUNK_ROUTE`, standard layout, auth required, no `nav`.

## Verification

- `npx vitest run --project unit`: 77 files, 1578 tests pass (preview 31, list/card 29, states 12, page 32).
- `npx tsc --noEmit` exits 0; `npm run build` exits 0; `git diff --stat -- web/package.json web/package-lock.json` is empty.
- `uv run python scripts/ci/run_all.py`: 7/7 gates pass (decisions 185 rows, no_sleep, placeholders).
- `grep -rn createObjectURL web/src` shows `use-page-image.ts` (plus the existing avatar helper); no `dangerouslySetInnerHTML`, `iframe`, `pdfjs`, `react-pdf` in the new code.
- The live-stack vitest project was not run.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Focus plan was dropped before the list changed.** The chunk switch answers before the list re-renders, so clearing the plan on its first effect run left focus on a removed control. The plan is now kept until the chunk has left the list and is dropped on a page, search or filter change. Commit 2ee145e.

**2. [Rule 3 - Blocking] `scrollIntoView` does not exist in jsdom.** The box scroll is guarded with a type check instead of failing the page. Commit 0a7a07f.

**3. [Rule 3 - Blocking] Fixture document ids are not 32 hex characters.** The inspector rejects them as the plan requires, so the page tests use their own hex document id; the shared fixtures were not changed. Commit 0a7a07f.

### Other differences

- **TDD order.** Tests were written before the implementation in all three tasks, and each RED commit holds only tests and test infrastructure (the `chunks` area, the `preview` extra in the `files` area).
- **Files outside the plan's list:** `components/page-header.tsx` (`titleClassName`, `titleHint` for a long name), `components/ui/segmented-control.tsx` (`testId`), `test/server-areas/files.ts` (`preview`), `DECISIONS.md` (R-185), and two test files split out of `chunk-inspector.test.tsx` (`chunk-list.test.tsx`, `chunk-states.test.tsx`).
- **No keys added for switch failures.** `inspector.switch.failed` and `inspector.editor.refused.*` already live in `failures.json`; plan 04-31 must not redefine them in `inspector.json`.
- **Route literal.** The acceptance grep for a `"/chunk"` literal in `routes.ts` is met through `CHUNK_ROUTE`, as the orchestrator required.
- **Not drawn yet (04-31):** the Edit button, "Add chunk", "Add a chunk by hand" and the editor.

## Known Stubs

None. The 'Add a chunk by hand' link and the edit controls are deliberately absent until plan 04-31.

## Threat Flags

None. Chunk text is a text node (hostile-markup test, T-04-30-01); `boxStyle` rejects non-finite and empty boxes and clamps to the page (T-04-30-02); images are blobs fetched with the Authorization header (T-04-30-03); nothing is requested before `bound` (T-04-30-04); the switch follows `useCanChangeDocument` and a 403 shows the lost-permission toast (T-04-30-05); object URLs are revoked and pages are kept 60 s (T-04-30-06).

## Notes for later plans

- 04-31: the chunk store is `chunkStateOf(server)` in `web/src/test/server-areas/chunks.ts`; `ChunkCard` takes no edit props yet and `ChunkList` is the place to add the editor card and "Add chunk".
- 04-32: `PagePreview` is controlled (`page`, `onPageChange`) and works without `selection`; `typeLabelOf` in `pages/chunk/inspector-states.tsx` is the upper-cased extension helper.
- Chinese strings in `inspector.json` are drafts for the B-18 review. Requirements were not ticked, per the orchestrator.

## Self-Check: PASSED

- Commits 6f90015, 39cea60, d633f2a, 2ee145e, 3e240af and 0a7a07f exist; all created files exist; full unit suite, type check, build and the 7 CI gates are green.
