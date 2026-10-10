---
phase: 03
scope: web
depth: standard
files_reviewed: 64
status: issues_found
critical: 0
warning: 4
info: 14
---

# Phase 3 Code Review — Frontend

Reviewed by the `gsd-code-reviewer` agent on 2026-10-10. The reviewer returned its findings in its report instead of writing this file; the orchestrator saved them here unchanged in substance. Nothing was run, built or exercised in a browser, so focus, drop-guard and autofill points are code-path reasoning only (B-31).

## What holds up

- A provider refusal is HTTP 400 with envelope code 101 (`api/apps/service_errors.py:23`); `http.ts` purges the session only on an HTTP 401 or envelope code 401 from a request that carried the current token.
- The provider key travels only in the PUT/POST body. The mutation uses `gcTime: 0` with `reset()` in `finally`; the form unmounts on close and aborts any in-flight call.
- The workspace store binds the persisted choice to the user id and clears it on every purge.
- No `dangerouslySetInnerHTML`, no `console.*` and no `any` in the reviewed paths.
- Every query key is scoped under `["ws", tenantId, …]`.
- Accepted limits B-31 to B-33, R-139 and R-152 were taken as written.

## Warnings

### FE-01 — Pagination and the gallery search box unmount on every page or search change, so keyboard focus is lost

**Files:** `web/src/pages/dataset/dataset-files.tsx:120,193-202`, `web/src/pages/datasets/index.tsx:147,163-201,230`, `web/src/hooks/use-document-request.ts:46`, `web/src/hooks/use-knowledge-request.ts:23`

**Scenario:** A keyboard user activates "Next". The query key changes and there is no `placeholderData`, so `isPending` becomes true. Pagination is rendered only when not pending, so the focused button is removed and focus drops to `<body>` after every page change. In the gallery, clearing a search on `/datasets?keywords=abc` (unfiltered page not cached) makes `showCreate` false during the load, which unmounts the `SearchInput`. `DatasetFiles` avoids this for its search box with `seenDocuments`; the gallery does not.

**Fix:** Add `placeholderData: keepPreviousData` to `useDatasetsRequest` and `useDocumentsRequest`; keep pagination and search mounted while fetching; apply `seenDocuments`-style logic to `showCreate` in the gallery.

### FE-02 — The active workspace is resolved in two steps, so a reload fires queries for the wrong workspace and wipes `page` and `keywords`

**Files:** `web/src/hooks/use-workspaces.ts:27-31,47-58`, `web/src/pages/datasets/index.tsx:66,72-90`, `web/src/hooks/use-knowledge-request.ts:23`

**Scenario:** The remembered workspace is a joined workspace W. The user reloads `/datasets?page=2&keywords=x`. Until the memberships query answers, `useActiveWorkspace()` falls back to the own workspace: the gallery, defaults and models queries fire for the own workspace, and the Models page briefly draws owner controls for it. When `initialise` sets W, the effect at lines 77-90 treats the change as a user switch and deletes `page` and `keywords` from the URL. `DatasetPage` guards this with `initialised`; the gallery and Models page do not.

**Fix:** Make `useActiveWorkspace()` return null until `initialisedFor !== null`, or add that condition to the `enabled` flag of the workspace-scoped hooks. In `DatasetsPage`, skip the reset when the previous tenant was the pre-initialisation fallback.

### FE-03 — Dataset create, update and delete refresh the cache only on success; a timeout or error leaves the gallery stale

**Files:** `web/src/hooks/use-knowledge-request.ts:47-55,68-76,95-106`, `web/src/services/dataset-service.ts:79,148,162,170`, `web/src/components/create-dataset-dialog/create-form.tsx:79-99`, `web/src/pages/datasets/errors.ts:49-66`

**Scenario:** Create waits up to 30 s for index provisioning. The client times out while the server finishes and creates the dataset. The dialog says the dataset wasn't created and the gallery is not invalidated; on retry the user gets `duplicate_name` for a dataset the gallery does not list. The same applies to a timed-out settings save or delete. The model hooks already use `onSettled` for this reason. Related: a create refused with 404 (workspace no longer joined) falls through to the generic copy.

**Fix:** Move the invalidation to `onSettled`, or invalidate in the failure handlers for status 0 and 5xx. Map a create 404 to the `workspace.forbidden` copy.

### FE-04 — `DeleteDocumentDialog` carries an old error into the next opening

**Files:** `web/src/components/delete-document-dialog.tsx:50,52-83`, `web/src/pages/dataset/dataset-files.tsx:203-216`

**Scenario:** Deleting document A fails with a 500, so `alert` is set. The user clicks "Keep document". `DatasetFiles` keeps the dialog mounted because `target` is never reset, and `alert` lives in the dialog component, so it survives the close. Opening delete for document B shows the old "wasn't deleted" alert before any attempt. `DeleteDatasetDialog` avoids this because its state lives in a body mounted only while open.

**Fix:** Reset `alert` when the dialog closes, or key the dialog on `target.id` and mount its state only while open.

## Info

- **FE-05 — Provider key input and password managers** (`web/src/pages/user-setting/model/provider-dialog.tsx:48-57`, UI-SPEC line 288). The key field is `type=password` with `autoComplete="off"`. Chromium-based browsers are documented to ignore `off` on password fields, so a saved devRag account password could be offered or autofilled into the key field and sent to the provider's address. Not confirmed in a real browser. Consider `autoComplete="new-password"` alongside the `data-1p-ignore` and `data-lpignore` attributes; this changes a locked UI-SPEC line.
- **FE-06 — Timeouts detected by comparing a localized string** (`web/src/services/http.ts:170`, `web/src/pages/user-setting/model/errors.ts:46`). `error.message === i18n.t("toast.timeout.title")` misclassifies if the language changes between failure and check. Add a `timedOut` or `kind` field to `ApiError`.
- **FE-07 — Pagination `<nav>` has no accessible name** (`web/src/components/ui/pagination.tsx:34`). Add `aria-label` through a prop or a default.
- **FE-08 — Model id limit is wrong for the composite id** (`web/src/pages/user-setting/model/schemas.ts:12,61-67`). The SPA allows a 128-character model name, but `common/model_ref.py` bounds the whole `model@provider` string to 128. A name over about 110 characters passes the form, is refused by the server and shows only the generic copy. Check against `128 - len("@" + slug)`.
- **FE-09 — Dataset detail cached under the wrong workspace key** (`web/src/pages/dataset/index.tsx:42,63`, `web/src/hooks/use-knowledge-request.ts:36`). On a deep link the detail is fetched under the active (own) workspace key and then seeded under the real one; the own-key copy is never removed, and later invalidations hit only the real key, so reopening the link can briefly show old `docNum` and limits. Remove the own-key entry when binding.
- **FE-10 — Cancelled upload rows and the "finishing" state** (`web/src/components/file-upload-dialog/upload-queue.ts:312,345`, `upload-row.tsx:93`). A row cancelled after the server stored the file shows "Cancelled", and Retry then stores a `name(1)` duplicate under D-14. A row in "finishing" has no per-row cancel, only the dialog-level Stop.
- **FE-11 — Raw English protocol text can reach an upload row** (`web/src/services/http.ts:255`, `upload-queue.ts:277`). `expectRecord` throws an `ApiError` with status 200 and an English "Malformed response from …" message; `classify` turns it into `kind: "message"`, so it shows verbatim and bypasses i18n. Map status 200 with code -1 to `{ kind: "server" }`.
- **FE-12 — Provider delete can be dismissed while the request is in flight** (`web/src/pages/user-setting/model/delete-provider-dialog.tsx:84-91`). Unlike the dataset and document delete dialogs, Esc and "Keep provider" are not blocked during the call.
- **FE-13 — Re-adding a file already in the list is ignored with no announcement** (`web/src/components/file-upload-dialog/index.tsx:88-95`). Per UI-SPEC line 506, but a screen-reader user gets nothing from the live region.
- **FE-14 — Duplicated helpers.** `parsePage`, `parseKeywords`, `MAX_PAGE`, `setPage` and `search` are copied in `web/src/pages/datasets/index.tsx:23-34,108-143` and `web/src/pages/dataset/dataset-workspace.tsx:21-32,69-95`; the keyword-length and page-size constants are duplicated across the dataset and document services.
- **FE-15 — Dead code.** `activeTenantId()` (`web/src/hooks/use-workspaces.ts:38`); `providerModelsPath` and `providerInstancePath` (`web/src/constants/api-paths.ts:66,74`); the `queuedKeys` parameter of `applyBatchLimits`, always `new Set()` (`web/src/components/file-upload-dialog/index.tsx:101`), and its `duplicates` result, always 0; `findProvider` is used only by a test.
- **FE-16 — Deep-link binding persists the workspace and can stick on "not found"** (`web/src/pages/dataset/index.tsx:58-70`, `web/src/stores/workspace-store.ts:140-146`). `bindActive` calls `setActive`, so opening a shared link writes the workspace into the remembered choice. If the membership list is stale, `unbindable` stays true until the id changes or the page reloads. Re-run the bind when the store's `memberships` change.
- **FE-17 — Live test helper listens on all interfaces** (`web/src/test/live/fake-provider.ts:88`). The fake provider binds to `0.0.0.0` so the app container can reach it, exposing the canned endpoint to the local network for the test duration. Bind to the docker bridge address.
- **FE-18 — Minor number formatting.** `formatBytes` shows "1,024 KB" just below a unit boundary (`web/src/components/file-upload-dialog/file-rules.ts:122-137`); `percentOf` rounds 0.996 up to 100% (`web/src/pages/dataset/document-row.tsx:26`), not reachable in Phase 3.

## Files not fully reviewed

- `web/src/constants/api-routes.generated.json`: generated, skipped.
- `web/src/constants/routes.ts`: reviewed through the Phase 3 diff only.
- `web/src/test/live/account.ts` and the three `*.live.test.ts` files under `web/src/test/live`: not read (not in the review list).
- `web/src/locales/en.json` was spot-checked; `zh.json` parity was not checked by the reviewer (the unit suite enforces it).
