---
phase: 03-models-knowledge-bases-and-upload
plan: 24
subsystem: ui
tags: [upload-dialog, dropzone, file-rules, upload-queue, document-service, progress, i18n]

requires:
  - phase: 03-models-knowledge-bases-and-upload
    provides: "03-16 upload API; 03-17 document list and delete API; 03-23 dataset service, query keys, api-paths and UI parts"
provides:
  - web/src/components/file-upload-dialog/ (FileUploadDialog, file-rules, upload-queue, dropzone, upload-row, stop-dialog)
  - web/src/components/ui/progress.tsx
  - web/src/services/document-service.ts (uploadDocument, listDocuments, deleteDocuments, DocumentView)
  - web/src/services/mapping.ts (shared coercions, extracted from dataset-service)
  - web/src/hooks/use-document-request.ts (documentsKeyRoot, documentsQueryKey, invalidateDocumentData, useInvalidateDocuments, useDocumentsRequest, useDeleteDocumentsRequest)
  - upload.* locale keys (en and zh, parity)
affects: [03-30 gallery, 03-25 delete document dialog, 03-31 dataset workspace page, 03-26 live journeys]

tech-stack:
  added: []
  patterns:
    - "Queue logic is plain TypeScript: a pure reducer, a synchronous external store (useSyncExternalStore) and a runner with an injected uploader"
    - "Document keys are [\"ws\", tenantId, \"documents\", datasetId, page, keywords]; upload and delete invalidate documents plus BOTH dataset keys"
    - "The dialog content is mounted only while open, so every opening starts with an empty queue and unmount aborts what is in flight"

key-files:
  created:
    - web/src/components/ui/progress.tsx
    - web/src/components/ui/progress.test.tsx
    - web/src/services/document-service.ts
    - web/src/services/document-service.test.ts
    - web/src/services/mapping.ts
    - web/src/hooks/use-document-request.ts
    - web/src/hooks/use-document-request.test.tsx
    - web/src/components/file-upload-dialog/file-rules.ts
    - web/src/components/file-upload-dialog/file-rules.test.ts
    - web/src/components/file-upload-dialog/upload-queue.ts
    - web/src/components/file-upload-dialog/upload-queue.test.ts
    - web/src/components/file-upload-dialog/dropzone.tsx
    - web/src/components/file-upload-dialog/upload-row.tsx
    - web/src/components/file-upload-dialog/stop-dialog.tsx
    - web/src/components/file-upload-dialog/index.tsx
    - web/src/components/file-upload-dialog/upload-dialog.test.tsx
  modified:
    - web/src/services/dataset-service.ts
    - web/src/locales/en.json
    - web/src/locales/zh.json

key-decisions:
  - "The 'Stop uploading?' confirmation is built on the Dialog primitive with role=alertdialog, not on ui/alert-dialog.tsx: npm resolves @radix-ui/react-alert-dialog to its own nested react-dialog 1.2.0 (focus-scope 1.2.0, dismissable-layer 1.1.20) while ui/dialog.tsx uses react-dialog 1.1.23. Two copies keep separate focus-scope stacks, so an AlertDialog layered over the upload Dialog never received focus and its Keep button could not close it (reproduced in a 25-line demo, then fixed by nesting a Dialog-primitive content). No package was touched."
  - "A run (batch) is tracked with a per-row `queued` flag: 'Upload n files' queues every Ready row; the counters 'Uploading {done} of {total}' count only queued rows and restart from zero when nothing is running or waiting. Files added during a run stay Ready until the next press."
  - "Batch room is counted against Ready rows (files per request) and against dataset.docNum + Ready + Uploading rows (documents per dataset); finished rows are left to the refetched docNum."
  - "A real 401 stops the queue (in flight aborted, waiting rows Cancelled) and adds no message of its own; the shared interceptor owns the session flow. 408, 5xx and 504 map to the retryable server message, status 0 to the connection message."
  - "Shared mapper coercions (text, count, asRecord, clampWhole) moved from dataset-service.ts to services/mapping.ts so the document service reuses them."

patterns-established:
  - "Server text (400 messages, limit messages) is trimmed to 300 characters and rendered as a text node; every other failure maps to fixed i18n copy"
  - "Hidden live region (data-testid upload-live) is fed by batch-level events only; the info alerts keep their own role=status"

requirements-completed: [DOC-01, DOC-02, DOC-03, SEC-06]
requirements-pending: [UI-12]

duration: ~75min
completed: 2026-10-09
---

# Phase 3 Plan 24: Upload Dialog Summary

**A native drag-and-drop upload dialog with per-file validation in the documented order, one POST per file with two in flight and `timeout: 0`, progress capped at 99% then Finishing, per-answer error mapping, a stop confirmation and a polite status region, backed by a document service and workspace-keyed hooks. No new package.**

## Performance

- **Tasks:** 3 of 3
- **Tests added:** 6 files, 140 tests (progress 5, rules 36, queue 37, service 10, hooks 4, dialog 48 including the close paths, overlay, focus and source gates)
- **Files:** 16 created, 3 modified

## Task Commits

1. **Task 1: failing tests (red)** - `9711e4a`. Red run: `Test Files 6 failed (6)`, each with `Failed to resolve import "./progress"`, `"./file-rules"`, `"./upload-queue"`, `"./document-service"`, `"./use-document-request"` and `"."` (no tests ran).
2. **Task 2: progress, document service, rules, queue** - `8032502` (7 files, 110 tests green with the dataset service and hook tests it touches)
3. **Task 3: dropzone, rows, dialog, stop dialog, locale keys** - `4473265` (dialog file 48 passed)

## Verification

- `npm run test -- --run`: `Test Files 50 passed (50)`, `Tests 980 passed (980)`, 0 failed (was 840 at the end of 03-23).
- `npm run typecheck`: exit 0. `npm run build`: exit 0 (existing chunk-size notice only).
- `git diff --stat -- web/package.json web/package-lock.json`: empty.
- `grep -rn "dangerouslySetInnerHTML\|react-dropzone" web/src web/package.json` outside tests: nothing (a source-gate test in the dialog file repeats it).
- `grep -n "timeout: 0" web/src/services/document-service.ts` -> line 85; `grep -n "Content-Type"` there -> nothing; `concurrency = 2` at `upload-queue.ts:277`.
- Test ids present: `upload-submit`, `upload-dropzone`, `upload-stop-dialog` and the rest of the UI-SPEC list, plus `upload-live`, `upload-close`, `upload-full`, `upload-stop-keep`, `upload-stop-confirm`.
- Not run: a real browser or the live stack (this plan is jsdom unit work; the live and Chrome journeys belong to 03-26 and 03-31, which can only exercise the dialog once the dataset page mounts it).

## Deviations from Plan

**1. [Rule 3 - Blocking] Stop confirmation is not the shared AlertDialog.** The plan said "the stop confirmation AlertDialog". With it, focus never moved to "Keep uploading" and clicking Keep did not close it. Cause found by `npm ls`: two copies of Radix dialog internals (alert-dialog nests react-dialog 1.2.0 with its own focus-scope and dismissable-layer; `ui/dialog.tsx` uses 1.1.23), so the layer stacks do not see each other. Rewrote it as `stop-dialog.tsx` on the Dialog primitive with `role="alertdialog"`, no corner close, outside clicks ignored, default focus on Keep. Same copy, same test ids, same behaviour. Upgrading or deduping the packages was not an option (D-21). 03-25's delete dialogs are standalone AlertDialogs (not layered over another dialog) and are not affected, but nobody should layer an AlertDialog over a Dialog without checking this.

**2. [Rule 1 - Bug avoided] Hard-coded-copy scan.** A type written as `=> Promise<{...}>` looked like JSX text to `no-hardcoded-copy.test.ts`; the type now has a named alias (`UploadResult`).

**3. Task 2 typecheck.** The plan expected `npm run typecheck` to exit 0 after Task 2, but the red dialog test (committed in Task 1) imports `"."`, which exists only after Task 3. Typecheck was clean again at Task 3. Tests of Task 2 files were green at their commit.

**4. Extras beyond the file list:** `use-document-request.test.tsx` (the hooks 03-25 and 03-31 reuse, including the invalidation of both dataset keys), `services/mapping.ts` (small refactor, dataset-service tests unchanged and green), and the exported `invalidateDocumentData` / `useInvalidateDocuments` helpers.

**5. Behaviour choices the plan left open:** the "Done" mode needs at least one finished row (an empty or all-rejected list still reads "Upload 0 files", disabled); a cancelled upload also refreshes the document list because the server may have stored the file; the 413 text uses the dialog's per-file limit.

Behaviour in the plan text that differs from the UI-SPEC: the plan's behavior list says 5xx "fails with the server message"; the UI-SPEC says fixed copy ("The server couldn't store this file. Try again."). The UI-SPEC was followed.

## API facts checked

- Upload: `documentUploadPath` resolved from the generated route table; response `data` is an array of document DTOs; reasons read from `ApiError.data.reason` (`dataset_limit`, `too_many_files` fail the remaining Ready rows; every other 400 shows the server message with a fallback).
- Nginx's `payload too large` answer arrives as HTTP 413 with envelope code 400 and no reason; classified by status, so it shows the size message.
- `upload_limits` come from `getDataset(id).uploadLimits` (03-23); null falls back to 100 MiB, 20 files, 10 000 documents and the 17 default extensions. Ready for 03-31 to pass `detail.uploadLimits`.

## Known Stubs

None. The dialog is complete but not yet reachable: no page mounts it until 03-31 (the Upload files button and the page-level drop overlay).

## Threat Flags

None beyond the plan's register: T-03-24-01 (names as text, grep gate and a hostile-name test), -03 (two in flight), -04 (`timeout: 0` asserted), -05 (window dragover and drop prevented while open, removed on close), -06 (401 not special-cased in the session flow; it only stops the queue).

## For the next plans

**Opening the dialog (03-30 does not need it; 03-31 and 03-25 do)**
```tsx
<FileUploadDialog
  dataset={{ id: detail.id, name: detail.name, docNum: detail.docNum }}
  limits={detail.uploadLimits}      // UploadLimitsView | null
  open={uploadOpen}
  onOpenChange={setUploadOpen}
  initialFiles={droppedOnPage}      // File[] | undefined; read once at opening
/>
```
Props type `FileUploadDialogProps`, import from `@/components/file-upload-dialog`. The dialog unmounts its content when `open` is false. It never closes itself; `onOpenChange(false)` is called by Done, Close, X, Esc, overlay (after the stop confirmation when uploads are unfinished) and "Stop uploads". The page should keep the dropped files in state and clear them in `onOpenChange(false)`. For the page-level drop overlay reuse `carriesFiles(dataTransfer)` and `readDropped(dataTransfer)` from `./dropzone` (folder detection included); hand the files over as `File[]` (folders are not detectable once converted, so filter `isDirectory` entries first or pass only files).

**Document service and hooks**
- `listDocuments({datasetId,page,pageSize,keywords}) -> {items: DocumentView[], total}`; `deleteDocuments(datasetId, ids) -> number` (all or nothing; silent, the caller shows the refusal and reads `ApiError.status` / `data.reason`); `uploadDocument(datasetId, file, {signal,onProgress})`.
- `DocumentView`: `id, name, size, type, suffix, run, progress, datasetId, createdBy, parserId, chunkNum, updateTime, createTime` (no token count, no location).
- Hooks: `DOCUMENTS_PAGE_SIZE = 20`; `useDocumentsRequest({datasetId, page, keywords})` (idle without an id); `useDeleteDocumentsRequest()` with `mutateAsync({datasetId, ids})`, which on success invalidates the documents root and BOTH dataset keys; `useInvalidateDocuments()` returns `(datasetId) => void`.
- Keys: `documentsKeyRoot(t, datasetId) = ["ws", t, "documents", datasetId]`, `documentsQueryKey(t, datasetId, page, keywords)`; the dataset keys stay in `use-knowledge-request.ts`.

**Locale keys:** everything this plan added is under `upload.*` (sub-groups `drop`, `reject`, `batch`, `state`, `row`, `error`, `stop`, `live`; plain `title`, `description`, `choose`, `full`, `submit`, `submitting`, `done`, `closeDialog`, `renamed`). The footer Close reuses `dialog.close`. `dataset.*`, `documents.*` and `datasets.*` keys are still owned by 03-30, 03-25 and 03-31.

**Test ids:** `upload-dialog, upload-dropzone, upload-input, upload-choose, upload-batch-notice, upload-rename-notice, upload-list, upload-row, upload-row-state, upload-row-progress, upload-row-remove, upload-row-cancel, upload-row-retry, upload-submit, upload-stop-dialog, upload-fatal, upload-live, upload-close, upload-full, upload-stop-keep, upload-stop-confirm`. Rows also carry `data-row-id`. The live tests in 03-26/03-31 should drive the real file input (`upload-input`) and not rely on the stub adapter's abort behaviour.

**Gotchas for later plans**
- Do not stack the shared `AlertDialog` over a `Dialog` (see deviation 1); stack a Dialog-primitive content or open it standalone.
- `Alert variant="info"` renders `role="status"`, so the dialog has several status elements; select the announcements with `upload-live`.
- UI-12 stays Pending in REQUIREMENTS.md until 03-31 mounts the dialog and a browser journey drives it.

## Self-Check: PASSED

Commits `9711e4a`, `8032502`, `4473265` and all files listed above exist; the full web suite (980 tests), typecheck and build were green after the last change.
