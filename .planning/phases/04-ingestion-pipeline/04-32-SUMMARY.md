---
phase: 04-ingestion-pipeline
plan: 32
subsystem: web
tags: [react, document-viewer, blob-url, download, text-preview, i18n]
requires:
  - phase: 04-30
    provides: PagePreview, usePageImage, typeLabelOf, InspectorNotFound
  - phase: 04-28
    provides: useDatasetBinding page shape
  - phase: 04-24
    provides: DOCUMENT_VIEWER_ROUTE, documentViewerPath
  - phase: 04-20
    provides: content endpoint (original, ?format=text), page images
provides:
  - "useBlobUrl / saveBlobAs: the single object-URL site for previews and downloads"
  - "TextPreview, ImagePreview, useDownload (abortable, single-flight, progress)"
  - "Document viewer page at /document?id=&doc= and its registered route"
  - "row-links.test.tsx: every row, menu, summary and inspector link matches a registered route"
  - "Test-server area content.ts (text, file blob with progress, holdable downloads)"
affects: []
tech-stack:
  added: []
  patterns: [object URL only in one hook after a type check, download re-typed as octet-stream before saving, body chosen by extension]
key-files:
  created:
    - web/src/components/document-preview/use-blob-url.ts
    - web/src/components/document-preview/use-download.ts
    - web/src/components/document-preview/text-preview.tsx
    - web/src/components/document-preview/image-preview.tsx
    - web/src/components/document-preview/preview-parts.test.tsx
    - web/src/pages/document-viewer/index.tsx
    - web/src/pages/document-viewer/download-button.tsx
    - web/src/pages/document-viewer/document-viewer.test.tsx
    - web/src/pages/dataset/row-links.test.tsx
    - web/src/test/server-areas/content.ts
    - web/src/locales/areas/en/viewer.json
    - web/src/locales/areas/zh/viewer.json
  modified:
    - web/src/components/document-preview/use-page-image.ts
    - web/src/constants/routes.ts
    - web/src/layouts/layouts.test.tsx
    - web/src/routes.test.tsx
    - .planning/DECISIONS.md
key-decisions:
  - "R-187: useBlobUrl is the one object-URL site; downloads are re-typed as application/octet-stream; text is a pre text node capped at 262144 characters; body chosen by extension"
requirements-completed: []
duration: ~45min
completed: 2026-10-19
---

# Phase 4 Plan 32: Document viewer Summary

Members can open `/document?id=&doc=` and see the original: page images for a PDF (also one with no readable text), file text for TXT, Markdown, CSV, JSON and HTML as literal text, the image for JPG and PNG, and a download card for every other type; Download streams the file as a blob with progress, ignores a second press and aborts when the user leaves.

## Tasks

1. **Blob URL hook, TextPreview, ImagePreview, download hook** (RED 43a490c, GREEN 8e2ab5a). `useBlobUrl` makes an object URL only for `image/jpeg` and `image/png`, revokes it on change and unmount; `usePageImage` now calls it and its Phase 4 tests pass unchanged. `saveBlobAs` (same file) re-types the blob as `application/octet-stream`, clicks a temporary `<a download>` and revokes. `TextPreview` renders a labelled, focusable `<pre>` (text node only, 262144-character cap, cut line, empty line, retryable error, eight-line skeleton). `ImagePreview` shows only JPEG or PNG, else the preview-error state. `useDownload` uses `timeout: 0`, an `AbortController` aborted on unmount, single flight, percent or null.
2. **Viewer page, route, journeys** (RED 353d648, GREEN 94df714). Back link, `PageHeader` with outline "View chunks" and "Download {name}", a meta `<dl>` (Type, Size, Uploaded, Status badge, Chunks, Method), then the body by type; `page` in the address is clamped to the page count; one `viewer-not-found` block (the inspector's) for malformed, unknown or foreign ids, with no request for malformed ones; page-level error with Try again; workspace bound before any request. `/document` is registered (`DOCUMENT_VIEWER_ROUTE`, standard layout, auth required, lazy, no `nav`) and the pinned route lists were updated. `row-links.test.tsx` proves the document name link, "View chunks", "Open document", "Parsing log" and the inspector's "Open document" all hit registered routes.

## Verification

- `npx vitest run --project unit`: 81 files, 1691 tests pass.
- `npx tsc --noEmit` and `npm run build` exit 0; `git diff --stat -- web/package.json web/package-lock.json` is empty.
- `uv run python scripts/ci/run_all.py`: 7/7 gates pass (decisions 187 rows).
- `createObjectURL` outside tests: `use-blob-url.ts` and the existing profile avatar helper only. No `dangerouslySetInnerHTML` or `iframe` in the new code.
- The live-stack vitest project was not run.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `Promise.withResolvers` is not in the TS lib target.** The loading-skeleton test used it and `tsc -b` (the build) failed; replaced with a plain promise. Commit 94df714.

### Other differences

- `saveBlobAs` is in `use-blob-url.ts` (not `use-download.ts`) so the download's temporary URL also respects the single-creation-site rule.
- `download-button.tsx` was split out of the page file; it is not in the plan's file list.
- The plan names `fetchContentBlob`, which does not exist; `downloadDocument` (04-20) is used for both downloads and image files.
- Extra locale keys beyond the UI-SPEC list: `viewer.documentTitleFallback`, `viewer.loading`. The detail error reuses `inspector.error.pageHeading`.
- A PDF whose detail has no page images (`preview` not `pages`) shows the download card.
- Requirements were not ticked, per the orchestrator. Chinese strings are drafts for B-18.

## Known Stubs

None.

## Threat Flags

None. Mitigations in place: text nodes only with a script payload test (T-04-32-01); images only for JPEG or PNG (T-04-32-02); every fetch uses the HTTP client and the save link is a blob URL (T-04-32-03); the stored name goes to `download` and the blob is re-typed (T-04-32-04); the download is aborted on leaving (T-04-32-05).

## Self-Check: PASSED

- Commits 43a490c, 8e2ab5a, 353d648 and 94df714 exist; all files listed above exist; full unit suite, type check, build and the 7 CI gates are green.
