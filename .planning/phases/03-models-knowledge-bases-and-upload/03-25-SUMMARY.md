---
phase: 03-models-knowledge-bases-and-upload
plan: 25
subsystem: ui
tags: [dataset-settings, delete-dataset, delete-document, actions-menu, permissions, alert-dialog, focus, i18n]

requires:
  - phase: 03-models-knowledge-bases-and-upload
    provides: "03-30 gallery card and create-dialog pieces (schema, ServerFieldError, error mapping); 03-24 document service and hooks; 03-23 dataset service, hooks and keys; 03-18 and 03-17 update and delete APIs"
provides:
  - web/src/components/dataset-actions-menu.tsx (DatasetActionsMenu)
  - web/src/components/dataset-settings-dialog (DatasetSettingsDialog, SettingsForm)
  - web/src/components/delete-dataset-dialog.tsx (DeleteDatasetDialog)
  - web/src/components/delete-document-dialog.tsx (DeleteDocumentDialog)
  - web/src/hooks/use-dataset-permissions.ts (canManageDataset, canRemoveDocument, useCanManageDataset, useCanRemoveDocument, useRoleIn, useWorkspaceName)
  - dataset-service updateDataset and deleteDatasets; useUpdateDatasetRequest, useDeleteDatasetsRequest, refreshDataset
affects: [03-31 dataset page, document table and workspace binding]

tech-stack:
  added: []
  patterns:
    - "A destructive confirmation is a standalone AlertDialog with no trigger; the owner passes onCloseAutoFocus and onSuccess"
    - "The delete dialog stops asking for the dataset detail (enabled=false, same key) the moment Delete is pressed, so removing the cached detail never triggers a refetch that would meet a 404"
    - "The actions menu is non-modal and does not hand focus back on a chosen item: the dialog it opens takes focus and returns it to the menu button when it closes"
    - "Failed deletes map to fixed copy only (deleteFailureOf): 403 lost-permission + refetch, 404 gone, 503 index_unavailable, anything else the failure sentence"

key-files:
  created:
    - web/src/components/dataset-actions-menu.tsx
    - web/src/components/dataset-settings-dialog/index.tsx
    - web/src/components/dataset-settings-dialog/settings-form.tsx
    - web/src/components/delete-dataset-dialog.tsx
    - web/src/components/delete-document-dialog.tsx
    - web/src/hooks/use-dataset-permissions.ts
    - web/src/pages/dataset/delete-dialogs.test.tsx
    - web/src/pages/dataset/settings-dialog.test.tsx
  modified:
    - web/src/services/dataset-service.ts
    - web/src/services/dataset-service.test.ts
    - web/src/hooks/use-knowledge-request.ts
    - web/src/hooks/use-llm-request.ts
    - web/src/components/page-header.tsx
    - web/src/pages/datasets/dataset-card.tsx
    - web/src/pages/datasets/index.tsx
    - web/src/pages/datasets/errors.ts
    - web/src/pages/datasets/datasets.test.tsx
    - web/src/locales/en.json
    - web/src/locales/zh.json

key-decisions:
  - "Document delete keys live under datasets.documentDelete.* and datasets.documentDeleted, not documents.delete.* / documents.deleted (UI-SPEC names): the existing value datasets.card.documents_one/_other ('{{count}} document(s)') makes the no-hardcoded-copy scan flag every source string that begins with a documents. key path. The gate is unchanged. Plan 03-31 will meet the same collision for its documents.* keys (see notes)."
  - "The settings save refetches (invalidates) the detail rather than writing the PUT answer into the cache: the detail carries upload_limits that the PUT answer lacks, and a write would drop them."
  - "The embedding model locks on docNum > 0 or chunkNum > 0 (chunkNum only when a detail view is passed); a late embedding_locked 409 shows under the field and refetches."
  - "Delete treats a 404 as already gone: refresh lists, close, call onSuccess, no success toast."

requirements-completed: [KB-06, KB-07, DOC-14, TEN-13, TEN-16]

duration: ~2h
completed: 2026-10-09
---

# Phase 3 Plan 25: Dataset Settings, Delete Dialogs and the Card Actions Menu Summary

**A creator, workspace owner or admin can rename a dataset, change who sees it and (while it is empty) its embedding model, or delete it after reading a freshly loaded document count; document deletion has its own named confirmation with fixed failure copy. The gallery card shows the actions menu only to those who may use it. No new package.**

## Accomplishments

- Service and hooks: `updateDataset(id, changes)` (PUT, only changed fields in snake_case, `null` clears the description, `timeout: 30000`, silent) and `deleteDatasets(ids, tenantId)` (DELETE `{ids, tenant_id}`, silent, resolves to the deleted ids). `useUpdateDatasetRequest` and `useDeleteDatasetsRequest` (one dataset per request) refresh the workspace lists and the detail; delete removes the cached detail.
- `DeleteDatasetDialog`: loads the detail on every opening, keeps Delete `aria-disabled` with a skeleton until a request started after opening has answered (a stale cached count never enables it), shows `Couldn't load the document count.` with Try again, three bodies (many, one, none), Keep dataset has initial focus, one request for a double press, 403 lost-permission alert plus refetch, 503 index message, any other failure the fixed sentence, 404 treated as gone.
- `DeleteDocumentDialog`: names the document and dataset, Keep document first, fixed failure copy "The document wasn't deleted. Nothing was removed. Try again." (checker flag 4), 403 and 404 handled like the dataset dialog, refreshes document pages and both dataset keys.
- `DatasetSettingsDialog` (`SettingsForm`): prefilled name, description, visibility and embedding model; Save settings `aria-disabled` until something differs; only changed fields sent; embedding is a select while empty and a read-only field with the helper once the dataset has documents; narrowing from Whole team to Only me shows the inline note; duplicate name under Name (focused), `model_unavailable` and `embedding_locked` under Embedding model (models refetched / detail refetched), 503 index message, 403 lost-permission alert, anything else the fixed fallback sentence.
- `DatasetActionsMenu` on the card (`relative z-10`, top right) only for `canManageDataset(dataset.createdBy, signed-in user id, role in dataset.tenantId)`: creator, owner, admin. The card owns the dialogs and returns focus to the menu button; after a delete the gallery moves focus to the page title (via `PageHeader`'s new optional `titleRef`) and the existing past-the-end logic steps back a page.

## Task Commits

| Task | Commit | Result |
|------|--------|--------|
| 1 Failing tests (dialogs, permissions, menu, service) | `45f3fee` | red |
| 2 Service, hooks, menu, delete dialogs, error mapping, locale keys | `349b396` | delete-dialogs, service, locale and no-hardcoded-copy green |
| 3 Settings dialog, card menu, page focus | `b30dc1b` | full suite green |

## Verification (real output)

Red run (`npm run test -- --run src/pages/dataset/delete-dialogs.test.tsx src/pages/dataset/settings-dialog.test.tsx src/services/dataset-service.test.ts src/pages/datasets`): `Failed to resolve import "@/components/delete-dataset-dialog"` and `"@/components/dataset-settings-dialog"`; `TypeError: updateDataset is not a function`, `TypeError: deleteDatasets is not a function`; `Unable to find an element by: [data-testid="dataset-actions"]` (10 times). `Test Files 4 failed (4)`, `Tests 18 failed | 34 passed (52)`.

Final, `cd web && npm run test -- --run`: `Test Files 54 passed (54)`, `Tests 1080 passed (1080)` (was 1024 at the end of 03-30). `npm run typecheck` exit 0. `npm run build` exit 0 (`built in 8.60s`, existing chunk-size advisory only). `git diff --stat -- web/package.json web/package-lock.json` empty. No `dangerouslySetInnerHTML` or `@tanstack/react-table` in production sources.

Not run: the live web tier and a real browser (this plan is jsdom unit work; the stack was not rebuilt). The focus return after a delete, the non-modal menu and the pointer lock behaviour are asserted in jsdom only.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Document delete keys renamed (no-hardcoded-copy scan)**
- **Found during:** Task 3 full-suite run
- **Issue:** the scan flags a source string that starts with a whole locale value; `datasets.card.documents_*` gives the value chunk `documents`/`document`, so any `"documents.delete.title"` literal (and `"document"` as a plain argument) is a hit.
- **Fix:** keys are `datasets.documentDelete.{title,body,keep,confirm,failed}` and `datasets.documentDeleted`; the internal subject token is `"doc"`. The gate is unchanged. English text is exactly the UI-SPEC copy.
- **Commit:** `349b396`

**2. [Rule 1 - Bug] Page lock left behind by a modal menu**
- **Found during:** Task 3 (gallery tests): `Unable to perform pointer interaction as the element has pointer-events: none` after opening the delete dialog from the menu.
- **Fix:** `DropdownMenu modal={false}`; the menu skips its own focus return when an item was chosen, the dialog returns focus to the menu button.
- **Commit:** `349b396`

**3. [Rule 1 - Bug] Focus after a delete never reached the page title**
- **Found during:** Task 3: focusing the title inside `onSuccess` was undone by the dialog's focus trap (still mounted) and the card then unmounted.
- **Fix:** the gallery records the deleted id and focuses the title in an effect once the card has left the list, one task later.
- **Commit:** `b30dc1b`

**4. [Rule 1 - Bug avoided] Refetch of a dataset being deleted**
- A removed (or invalidated) detail query with an active observer refetches and meets a 404. `useDatasetRequest(id, enabled)` gained an `enabled` argument; the dialog disables the query (same key) when Delete is pressed and keeps the last count for the closing animation.

**5. [Rule 2] Test change in 03-30's card test.** The 03-30 assertion `queryByRole("button") === null` on a card meant "no stub menu"; the creator's card now carries exactly the actions button, so it asserts `["dataset-actions"]`.

**6. Plan items interpreted**
- "useUpdateDatasetRequest writes the detail into the cache" became invalidation of the detail and lists (the PUT answer has no `upload_limits`).
- The settings dialog takes `DatasetView | DatasetDetailView`; `chunkNum` is checked only when present.
- Added beyond the file list: `hooks/use-dataset-permissions.ts`, `dataset-settings-dialog/settings-form.tsx` (no giant file), `PageHeader` `titleRef`, `useModelsRequest(type, enabled)`, `refreshDataset`.
- Locale keys added beyond the UI-SPEC table: `datasets.form.settingsBody`, `datasets.error.locked`, `datasets.settings.failed|indexDown|gone`, `datasets.delete.loading`.

## Known Stubs

None. The dialogs are complete; the dataset page (03-31) is the only other place that mounts them, so the document delete dialog is not yet reachable from any page.

## Threat Flags

None beyond the register: T-03-25-01 (names as text nodes; hostile-name tests; no `dangerouslySetInnerHTML`), -02 (controls derived from creator and role, a 403 shows the lost-permission alert and refetches in both dialogs), -03 (Delete disabled until a fresh count loads, stale cache never enables it), -04 (named AlertDialogs, default focus on the keep action, one request per press).

## Notes for plan 03-31

- **Open the dialogs (controlled, no trigger):**
  - `DeleteDatasetDialog({ dataset: { id, name, tenantId }, open, onOpenChange, onSuccess?, onCloseAutoFocus? })` in `@/components/delete-dataset-dialog`. `onSuccess` fires after the dataset is gone (also on a 404); navigate to `DATASETS_PATH` there. Pass `onCloseAutoFocus` and decide focus; on the dataset page the delete removes the detail query from the cache, so make sure the page's own `useDatasetRequest` does not refetch it (pass `enabled` false once `onSuccess` ran, or navigate in `onSuccess`).
  - `DatasetSettingsDialog({ dataset: DatasetView | DatasetDetailView, open, onOpenChange, onCloseAutoFocus? })` in `@/components/dataset-settings-dialog`. A success invalidates `datasetsKeyRoot` and `datasetQueryKey`, so the page title updates by itself.
  - `DeleteDocumentDialog({ datasetId, datasetName, document: { id, name }, open, onOpenChange, onSuccess?, onCloseAutoFocus? })` in `@/components/delete-document-dialog`. It refreshes documents, `datasets` and the detail. On `onSuccess` the table moves focus to its caption and steps back a page if it emptied (the dialog does neither).
  - `DatasetActionsMenu({ name, onSettings, onDelete, triggerRef? })` in `@/components/dataset-actions-menu`; test ids `dataset-actions` (trigger), `dataset-menu`, `dataset-menu-settings`, `dataset-menu-delete`. The UI-SPEC lists `dataset-menu*` for the workspace page too, so reuse it there.
  - Do not render an AlertDialog while a Dialog is open (two Radix copies); the card closes the menu first.
- **Permission helpers** (`@/hooks/use-dataset-permissions`): `canManageDataset(createdBy, userId, role)`, `canRemoveDocument(datasetCreatedBy, documentCreatedBy, userId, role)`, hooks `useCanManageDataset({createdBy, tenantId})`, `useCanRemoveDocument(dataset, { createdBy })`, `useRoleIn(tenantId)`, `useWorkspaceName(tenantId)`. Draw the document delete control only where `useCanRemoveDocument` is true (absent, not disabled).
- **Test ids:** `dataset-delete-dialog`, `dataset-delete-count`, `dataset-delete-count-skeleton`, `dataset-delete-confirm`, `dataset-delete-keep`, `dataset-delete-retry`, `dataset-delete-error`, `document-delete-dialog`, `document-delete-confirm`, `document-delete-keep`, `document-delete-error`, `dataset-settings-dialog`, `dataset-settings-form`, `dataset-settings-skeleton`, `dataset-settings-submit`, `dataset-settings-error`, `dataset-settings-embedding-fixed`, `dataset-settings-narrowing`, plus the create dialog's field ids `field-dataset-name|description|embedding|visibility`.
- **Locale prefixes used here:** `datasets.menu.*`, `datasets.card.actions`, `datasets.form.settingsTitle|settingsBody`, `datasets.settings.*`, `datasets.visibility.narrowing`, `datasets.field.embeddingFixed`, `datasets.error.locked`, `datasets.delete.*`, `datasets.deleted`, `datasets.documentDelete.*`, `datasets.documentDeleted`. Not added: `datasets.errorNoun.one`, `dataset.*` and `documents.*` (03-31).
- **Key collision to expect:** `datasets.card.documents_one/_other` makes the no-hardcoded-copy scan reject any source string that starts with `documents.` (or the bare word `document`/`documents`). The UI-SPEC's `documents.search`, `documents.caption`, `documents.col.*`, `documents.empty.*` and so on will hit it in components and pages. Do not weaken the gate; either choose non-colliding key prefixes (as done here with `datasets.documentDelete.*`) or have the orchestrator decide on a deliberate gate refinement for key paths.
- `PageHeader` accepts `titleRef` (makes the h1 script-focusable); `useDatasetRequest(id, enabled)` and `useModelsRequest(type, enabled)` accept an `enabled` flag.

## Self-Check: PASSED

Files present: the eight created paths above exist (checked with git status clean after the commits). Commits `45f3fee`, `349b396`, `b30dc1b` exist in `git log`.
