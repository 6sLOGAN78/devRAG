---
phase: 03-models-knowledge-bases-and-upload
plan: 31
subsystem: ui
tags: [dataset-workspace, document-table, status-badge, drop-overlay, workspace-binding, deep-link, sidebar, i18n]

requires:
  - phase: 03-models-knowledge-bases-and-upload
    provides: "03-24 upload dialog, document service and hooks; 03-25 settings, delete dialogs, actions menu and permission helpers; 03-30 gallery, app-paths and datasetFilesPath; 03-23 dataset service and hooks; 03-03 workspace store and selector"
provides:
  - web/src/pages/dataset/index.tsx (DatasetPage at /dataset/files?id=, workspace binding)
  - web/src/pages/dataset/dataset-workspace.tsx (DatasetWorkspace: header, meta, dialogs, page-level drop target)
  - web/src/pages/dataset/dataset-files.tsx (DatasetFiles: search, paging, delete icons, states)
  - web/src/pages/dataset/document-row.tsx, document-status-badge.tsx, page-states.tsx, errors.ts (datasetPageState)
  - route /dataset/files (standard layout, auth required, no nav) and the sidebar's nested-path match
  - workspace store bindActive / clearBound; the header selector announces a bound switch
affects: [03-26 live and real-Chrome journeys, 03-28, 03-29]

tech-stack:
  added: []
  patterns:
    - "Binding by ref: boundTenantRef is written before the store changes; the leave-for-/datasets effect reads the store and compares it with the ref, so only a user switch navigates"
    - "The detail query is not watched while the delete dialog is open or after the dataset is gone, and the last copy keeps drawing until the page leaves"
    - "The table owns its documents query and reports 'empty' upward (onEmptyChange) so the page can hide the header Upload action"
    - "Page-level file drops: depth counter, overlay with pointer-events-none, ignored while any modal is open; window dragover/drop guard against the browser opening a missed drop"

key-files:
  created:
    - web/src/pages/dataset/index.tsx
    - web/src/pages/dataset/dataset-workspace.tsx
    - web/src/pages/dataset/dataset-files.tsx
    - web/src/pages/dataset/document-row.tsx
    - web/src/pages/dataset/document-status-badge.tsx
    - web/src/pages/dataset/page-states.tsx
    - web/src/pages/dataset/errors.ts
    - web/src/pages/dataset/dataset-files.test.tsx
    - web/src/pages/dataset/dataset-workspace.test.tsx
    - web/src/test/dataset-server.ts
  modified:
    - web/src/constants/routes.ts
    - web/src/components/app-sidebar.tsx
    - web/src/components/workspace-switch.tsx
    - web/src/components/page-header.tsx
    - web/src/components/file-upload-dialog/index.tsx
    - web/src/stores/workspace-store.ts
    - web/src/stores/workspace-store.test.ts
    - web/src/layouts/layouts.test.tsx
    - web/src/locales/en.json
    - web/src/locales/zh.json

key-decisions:
  - "Document-table copy lives under datasets.files.* (the orchestrator's locale key rule); the dataset page copy is under dataset.*. English text is the UI-SPEC text."
  - "A deep link switches the workspace through a new store action bindActive, which flags `bound`; WorkspaceSwitch announces 'Switched to {workspace}' from that flag (its announcer was local state, so a page could not reach it)."
  - "The sidebar renders Link with an explicit aria-current instead of NavLink: NavLink only sets aria-current for its own match, so it cannot mark Datasets current on /dataset/files."
  - "A dataset whose workspace the membership list does not contain (bindActive refuses) renders the same 'Dataset not found' block and binds nothing."

patterns-established:
  - "Controls the caller may not use are absent: actions menu via useCanManageDataset, row delete via useCanRemoveDocument; Upload files for every member who can see the dataset"
  - "Page url params: id (32 lowercase hex, else not found with no request), page and keywords clamped before any request"

requirements-completed: [UI-11, UI-12, KB-05, DOC-08, DOC-14, TEN-13, TEN-16]

duration: ~1h
completed: 2026-10-09
---

# Phase 3 Plan 31: Dataset Workspace Page Summary

**`/dataset/files?id=` shows a dataset's name, visibility, count, embedding model and description over a searchable, paged (20) document table with "Not started" badges and 0% progress, opens the upload dialog from a button, the empty state or a page-level file drop, mounts the settings and delete dialogs for those who may use them, and follows a deep link into a joined workspace without looping. No new package.**

## Accomplishments

- `DatasetPage`: a missing, malformed (not 32 lowercase hex) or foreign `id`, a 404 and a dataset of an unjoined workspace all render one `dataset-not-found` block (h1 "Dataset not found", primary "Back to datasets"); a malformed id sends no request; a 5xx is a page-level `ErrorState` ("this dataset") with Try again; the title is "{name} - devRag".
- `DatasetFiles`: `<caption>` "Documents in {name}", six `scope="col"` headers, file name as a text node (`break-all line-clamp-2`, full name in `title`), size via `formatBytes`, a dated `<time>`, `DocumentStatusBadge` (run "0" is "Not started" with a hollow circle, anything else an outline "Unknown status"; no Parse control), progress `{n}%`, delete icon only where `useCanRemoveDocument` is true, search (debounced), 20 per page, empty state ("No documents yet" with the per-file size and an Upload files action), no-match state with Clear search, in-place error, skeleton (header plus five rows), automatic step-back when a page empties, focus to the caption after a delete and back to the row's icon after Keep document.
- Header: back link, name, `DatasetActionsMenu` (creator, owner, admin) opening the 03-25 settings and delete dialogs (delete leaves for `/datasets` with replace), primary Upload files (hidden while the empty state shows its own), meta line (badge, plural count, "Embedding model" and the id in mono), description.
- Upload: header button, empty-state action and a page drop open `FileUploadDialog` with `detail.uploadLimits`; the dropped files are cleared when it closes; `dataset-drop-overlay` (2 px primary border, `bg-background/80`, "Drop files to upload to {name}") for file drags only, ignored while any dialog is open, and a window guard so a missed drop never makes the browser open the file.
- Workspace binding (D-26) with `boundTenantRef`: written before the store changes, detail seeded under the new workspace key, store switched through `bindActive`, announcement through the selector; the leave effect compares the store with the ref. Deep link into a joined workspace stays; a later user switch navigates with replace; an own-workspace dataset sets and announces nothing.
- Route `/dataset/files` (standard, auth required, no nav) and Datasets highlighted on any `/dataset/` path.

## Task Commits

| Task | Commit | Result |
|------|--------|--------|
| 1 Failing tests (files, workspace, layouts) | `5a1e4c6` | red |
| 2 Badge, page-state mapping, document table, keys | `9aa5cd0` | dataset-files, locales, no-hardcoded-copy green |
| 3 Page, binding, drop overlay, route, sidebar, keys | `604ec18` | full suite green |

## Verification (real output)

Red run (`npm run test -- --run src/pages/dataset/dataset-files.test.tsx src/pages/dataset/dataset-workspace.test.tsx src/layouts`): `Failed to resolve import "./document-status-badge" from "src/pages/dataset/dataset-files.test.tsx"`, `Failed to resolve import "." from "src/pages/dataset/dataset-workspace.test.tsx"`; layouts: `expect(element).toHaveAttribute("aria-current", "page")` for `/dataset/files` and `expected [ '/', '/login', …(9) ] to deeply equal [ '/', '/login', …(10) ]`. `Test Files 3 failed (3)`, `Tests 2 failed | 24 passed (26)`.

Task 2: `dataset-files.test.tsx` plus locales, `Test Files 2 passed (2)`, `Tests 22 passed (22)`; `src/constants` (no-hardcoded-copy) 6 passed.

Final, `cd web && npm run test -- --run`: `Test Files 56 passed (56)`, `Tests 1135 passed (1135)` (was 1080). `npm run typecheck` exit 0. `npm run build` exit 0 (`built in 10.71s`, the existing chunk-size advisory only). `git diff --stat -- web/package.json web/package-lock.json` empty. No `dangerouslySetInnerHTML` or `@tanstack/react-table` in sources. `grep -n boundTenantRef web/src/pages/dataset/index.tsx`: the ref definition (line 37), the write before the store update (line 61, then `bindActive` at 65) and the comparison in the leave effect (line 75). `/dataset/files` in `routes.ts` has no `nav`.

Not run: the live stack and a real browser (jsdom unit work; plan 03-26 drives them). Drag and drop is simulated with synthetic events; the real file drop, the focus return after the dialogs and the window drop guard need a real browser.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking, orchestrator rule] Document copy keys renamed.** The plan and UI-SPEC name `documents.*`; the no-hardcoded-copy scan rejects that prefix (existing value `datasets.card.documents_*`). Keys are `datasets.files.{search,caption,loading,col.*,status.*,deleteLabel,empty.*,noMatch.*,error.heading}`; the UI-SPEC's `documents.errorNoun` became the full-sentence `datasets.files.error.heading` ("Couldn't load documents"), the same text the noun form produces. The scan is unchanged. Reused: `datasets.documentDelete.*`, `datasets.documentDeleted`, `datasets.card.documents`, `datasets.visibility.*`, `common.*`.

**2. [Rule 2 - Missing critical] The deep-link announcement had no path to the selector.** The UI-SPEC and the plan's test say the announcer reads "Switched to ...", but the `workspace-announcer` text is local state of `WorkspaceSwitch`, set only by its own menu. Added `bindActive(tenantId)` / `clearBound()` and a `bound` flag to the workspace store (a real change sets it) and an effect in `WorkspaceSwitch` that announces and clears it. Two store tests added.

**3. [Rule 3 - Blocking] Sidebar match.** `NavLink` sets `aria-current` only for its own match, so it cannot mark Datasets on `/dataset/files`. `AppSidebar` now renders `Link` with `aria-current` from an exported `isNavActive(entryPath, pathname)` (equal, below, or a registered nested prefix: `/datasets` owns `/dataset/`). `/dataset` and `/datasetsx` do not match. All existing layout tests pass unchanged.

**4. [Rule 2 - Missing critical] `FileUploadDialog` gained an optional `onCloseAutoFocus`.** Opened by a drop there is no focused opener to return to; the page returns focus to the header Upload button, the opener, or the title.

**5. [Rule 1 - Bug avoided] The detail is not watched during a delete.** `useDatasetRequest(id, enabled)` is disabled while the delete dialog is open and after `onSuccess`; the last copy keeps drawing so the dialog is not unmounted under itself. A test asserts no further detail request after the delete.

**6. Other additions beyond the file list.** `document-row.tsx`, `dataset-workspace.tsx`, `page-states.tsx` (no giant files); `src/test/dataset-server.ts` (shared in-memory server for the two page test files, outside the copy scan); `PageHeader` h1 got `min-w-0 break-words` (long dataset names); `DatasetFiles.onPageChange(page, { replace })` so an automatic step-back replaces the history entry; extra keys `dataset.documentTitleFallback`, `dataset.loading`, `dataset.error.heading`, `datasets.files.loading`.

**7. Plan items interpreted.**
- "no flash and no refetch" after the silent switch: the detail is seeded under the new key so there is no flash; React Query's default `staleTime` of 0 still revalidates it once in the background (two detail requests at most, asserted). Raising `staleTime` globally would change the 03-25 fresh-count rule, so it was not touched.
- Folders dropped on the page: the dialog accepts `File[]` only, so folder entries are filtered out and not reported as rejected rows (the dialog's own dropzone still reports them). Recorded as a limitation.
- A store that is not yet initialised (membership list not loaded) refuses every switch, so binding waits for it; the table is held on a skeleton until the active workspace equals the dataset's.

## Known Stubs

None. `dataset-upload` is both the header button and the empty-state action (they never exist together).

## Threat Flags

None beyond the register. T-03-31-01 (one not-found block for 404, malformed id and unbindable workspace; malformed id sends no request, tested), -02 (names as text nodes, hostile-name tests, grep gate), -03 (controls from creator, uploader and role; 403 shows the lost-permission alert and refetches), -04 (leave on a user switch via the ref comparison; `["ws", tenantId, ...]` keys), -05 (drag handlers and the window guard prevent the default open).

## Notes for plan 03-26 (live and real-Chrome journeys)

- **Routes:** `/dataset/files?id={32 hex}` (`&page=`, `&keywords=`); `/datasets` for the way back (also where a dataset delete and a user workspace switch land, with replace). The gallery card link is `dataset-card-link`.
- **Test ids (page):** `dataset-page`, `dataset-back`, `dataset-meta`, `dataset-upload` (header button or empty-state action), `dataset-actions`, `dataset-menu`, `dataset-menu-settings`, `dataset-menu-delete`, `dataset-not-found`, `dataset-page-skeleton`, `dataset-drop-overlay`, `error-state`, `empty-state`. **Table:** `documents-search` (wrapper; the input is the `searchbox` named "Search documents"), `documents-table`, `document-row`, `document-status`, `document-progress`, `document-delete`, `document-row-skeleton`, `documents-skeleton`. **Dialogs:** `document-delete-dialog`, `document-delete-confirm`, `document-delete-keep`, `document-delete-error`, `dataset-delete-dialog`, `dataset-delete-count`, `dataset-delete-confirm`, `dataset-settings-dialog`, and the upload set (`upload-dialog`, `upload-input`, `upload-submit`, `upload-row`, `upload-row-state`, `upload-close`, `upload-rename-notice`, ...). The table caption is the sr-only "Documents in {name}" and takes focus after a delete.
- **Copy to wait on:** "Not started" and "0%" for every document; "Uploaded" / "Uploaded as {newName}" rows in the dialog; "Dataset not found"; the delete body states the count read after the dialog opened ("... and its N documents ...").
- **Only a real browser can confirm:** a real file drop onto the page (overlay, dialog opens with the file queued, a folder drop is dropped silently), the window drop guard (a drop on the header does not open the file), focus return after the upload, settings and delete dialogs, the deep link into a joined workspace in a fresh load (store initialisation order with the real membership request), and the document list refresh after an upload of more than 10 s.
- **Live data shape:** dataset ids are 32 lowercase hex; document `progress` is a fraction of one (the table shows whole percent); a member sees the actions menu only after the membership list has loaded.

## Self-Check: PASSED

Files present (checked with `git status`, clean after the commits) and commits `5a1e4c6`, `9aa5cd0`, `604ec18` exist in `git log`. The full web suite (1135 tests), typecheck and build were green after the last change.
