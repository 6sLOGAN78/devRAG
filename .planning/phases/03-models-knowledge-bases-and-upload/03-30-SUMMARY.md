---
phase: 03-models-knowledge-bases-and-upload
plan: 30
subsystem: ui
tags: [datasets-gallery, create-dataset-dialog, blocked-form, error-targets, workspace-scoped, nav-order, i18n]

requires:
  - phase: 03-models-knowledge-bases-and-upload
    provides: "03-23 parts, dataset service and hooks; 03-20 LlmSelect, info Alert, model hooks; 03-14 dataset API reasons; 03-13 defaults API; 03-03 workspace store"
provides:
  - web/src/pages/datasets (DatasetsPage, DatasetCard, datasetErrorTarget)
  - web/src/components/create-dataset-dialog (CreateDatasetDialog, CreateForm, BlockedForm, ServerFieldError, datasetSchema)
  - web/src/constants/app-paths.ts (DATASETS_PATH, MODEL_SETTINGS_PATH, datasetFilesPath)
  - nav entry Datasets (/datasets, Database, Platform group, order 2)
affects: [03-25 dataset actions menu and settings dialog, 03-31 dataset workspace page and live journey]

tech-stack:
  added: []
  patterns:
    - "Server refusals are placed by one errors module (status + data.reason) into name, embedding, blocked or alert; server text appears only in an alert, bounded to 160 characters, as a text node"
    - "URL params (page, keywords) are clamped before any request; a workspace switch resets them"
    - "The form-or-blocked choice is made once when defaults and models first arrive, so a later refetch keeps the form and its message"

key-files:
  created:
    - web/src/constants/app-paths.ts
    - web/src/pages/datasets/index.tsx
    - web/src/pages/datasets/dataset-card.tsx
    - web/src/pages/datasets/errors.ts
    - web/src/pages/datasets/datasets.test.tsx
    - web/src/components/create-dataset-dialog/index.tsx
    - web/src/components/create-dataset-dialog/create-form.tsx
    - web/src/components/create-dataset-dialog/blocked-form.tsx
    - web/src/components/create-dataset-dialog/server-field-error.tsx
    - web/src/components/create-dataset-dialog/schemas.ts
    - web/src/components/create-dataset-dialog/create-dataset-dialog.test.tsx
  modified:
    - web/src/constants/routes.ts
    - web/src/hooks/use-llm-request.ts
    - web/src/components/llm-select/index.tsx
    - web/src/layouts/layouts.test.tsx
    - web/src/components/shell-i18n.test.tsx
    - web/src/routes.test.tsx
    - web/src/locales/en.json
    - web/src/locales/zh.json

key-decisions:
  - "The blocked form is also shown when the saved default embedding model no longer exists in the workspace (nothing is guessed, D-18)"
  - "Server field errors (duplicate name needs the dataset name interpolated) render through ServerFieldError with the finished sentence; the RHF error is set with an empty message so aria-invalid and aria-describedby still work"
  - "Radix modal dialogs return focus to a trigger only; with no DialogTrigger the page passes onCloseAutoFocus and restores focus to the opener (or the header Create button if the empty-state one was replaced)"
  - "The gallery error heading uses a full-sentence key datasets.error.loadList instead of the planned datasets.errorNoun.list: the noun value 'datasets' collides with the no-hardcoded-copy scan (every key path 'datasets.x' contains it)"

requirements-completed: [UI-10, KB-01, KB-02, KB-04, TEN-13, TEN-16]

duration: ~1h
completed: 2026-10-09
---

# Phase 3 Plan 30: Datasets Gallery and Create Dialog Summary

**The /datasets gallery (12 per page, page and keywords in the URL, workspace scoped) and a create dialog that preselects the workspace's explicit default embedding model, explains a missing default in a blocked form, and places server refusals by status and reason; no new package.**

## Accomplishments

- Gallery: eight skeleton cards, empty state with Create action, no-match state with Clear search, in-place error with Try again, previous/next paging, debounced search, automatic step-back when the requested page is past the end, malformed `page` treated as 1, `keywords` cut to 128 characters, workspace switch resets both.
- Card: `article` with one name link covering the card, two-line description (omitted when empty), visibility badge (Lock/Users), plural document count and localized updated date.
- Create dialog: name focused on open, description counter from 400 of 500, embedding preselected to the workspace default, visibility defaults to Only me, in-flight guard, `aria-busy`, 30 s timeout (service), success toast then navigation to `/dataset/files?id=`.
- Errors: `duplicate_name` under Name (focused), `model_unavailable` under Embedding model with a model refetch (stale selection cleared), `dimension_unsupported` under Embedding model, `no_default_embedding` switches to the blocked form, `index_unavailable`, 403, `busy`, `dataset_invalid` and anything else as alerts.
- Missing default: info notice in the gallery (link for owner and admin, Ask sentence for members) and the matching blocked dialog form.
- Nav: Home 1, Datasets 2, System status 3, Profile 4, Models 5, API tokens 6, Team 7, updated deliberately in the three pinned tests.

## Task Commits

| Task | Commit | Result |
|------|--------|--------|
| 1 Failing tests (dialog, gallery, nav order) | `8d9dd81` | red |
| 2 Errors, schema, dialog, locale keys | `0db12ff` | dialog and locale tests green |
| 3 Gallery, card, route, nav | `dbf9a91` | full suite green |

## Verification (real output)

Red run (`npm run test -- --run src/components/create-dataset-dialog src/pages/datasets src/layouts src/components/shell-i18n.test.tsx src/routes.test.tsx`): `Failed to resolve import "." from "src/components/create-dataset-dialog/create-dataset-dialog.test.tsx"`, same for `src/pages/datasets/datasets.test.tsx`; `Test Files 5 failed (5)`, `Tests 6 failed | 44 passed (50)` (nav-order assertions: `expected [ Array(6) ] to deeply equal [ 'nav.home', 'nav.datasets', ...(5) ]`, `Unable to find an element by: [data-testid="nav-item-datasets"]`).

Final, `cd web && npm run test -- --run`: `Test Files 52 passed (52)`, `Tests 1024 passed (1024)`. `npm run typecheck` exit 0. `npm run build` exit 0 (`built in 8.50s`, only the existing chunk-size advisory). `git diff --stat -- web/package.json web/package-lock.json` is empty. No `dangerouslySetInnerHTML` or `font-medium` in the new files.

Not run: live web tier (this plan is web unit work; the stack was not rebuilt).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Locale value `datasets` tripped the no-hardcoded-copy scan**
- **Found during:** Task 3 full-suite run
- **Issue:** `datasets.errorNoun.list` = "datasets" matches every `"datasets.*"` key string in the scanned sources.
- **Fix:** replaced it by `datasets.error.loadList` = "Couldn't load datasets" passed as the `ErrorState` heading; the English text is identical. The gate itself is unchanged.
- **Files:** pages/datasets/index.tsx, locales/en.json, locales/zh.json
- **Commit:** `dbf9a91`

**2. [Rule 1 - Bug] Focus was not returned to the opener**
- **Found during:** Task 3 (gallery test)
- **Issue:** Radix modal `onCloseAutoFocus` returns focus to a `DialogTrigger` only; there is none.
- **Fix:** `CreateDatasetDialog` takes `onCloseAutoFocus`; the page restores focus to the opener or the header Create button.
- **Commit:** `dbf9a91`

**3. [Rule 2 - Missing critical] Nav tests that assumed `/datasets` was unbuilt**
- `routes.test.tsx` Not Found case and `layouts.test.tsx` "another path" case now use `/chat`; a test marking Datasets current on `/datasets` was added; the "never renders unbuilt entries" list no longer names Datasets.

### Additions not in the UI-SPEC key tables (to record)

- `datasets.form.createBody` (dialog description so every dialog has one), `datasets.form.loading` and `datasets.loading` (sr-only loading status), `datasets.error.dimension` (for `dimension_unsupported`), `datasets.error.loadList`. en and zh parity holds.
- `LlmSelect` now forwards `aria-invalid`; `use-llm-request.ts` exports `modelsKeyRoot`. `constants/app-paths.ts` holds the shared in-app paths so pages need not import the route registry.
- `datasets.errorNoun.list` was not added (see deviation 1); `datasets.errorNoun.one` is left to plans 03-25 and 03-31 (use a full-sentence key as well if its value collides).

## Known Stubs

None. No actions menu or disabled stub exists on the card (plan 03-25 owns it). The card links to `/dataset/files?id=`, whose page arrives in plan 03-31 (until then the path shows Not Found).

## Threat Flags

None. T-03-30-01 to -05 are covered: text nodes only (hostile name, description and server message tests), `["ws", tenantId]` keys with URL reset on switch, clamped `page` and `keywords`, member sees no owner link, `inFlight` guard.

## Notes for plans 03-25 and 03-31

- Card: `DatasetCard({ dataset: DatasetView })` in `web/src/pages/datasets/dataset-card.tsx`. Mount the actions menu inside the `<article>` (it is `relative`), positioned top-right with `relative z-10` above the link layer; render it only for the creator (`dataset.createdBy === user.id`), owners and admins. Test ids in use: `datasets-page`, `datasets-missing-default`, `datasets-search`, `dataset-grid`, `dataset-grid-skeleton`, `dataset-card-skeleton`, `dataset-card`, `dataset-card-link`, `dataset-create`, `create-dataset-dialog`, `create-dataset-form`, `create-dataset-skeleton`, `create-dataset-blocked`, `create-dataset-error`, `field-dataset-name`, `field-dataset-description`, `field-dataset-embedding`, `field-dataset-visibility`, `create-dataset-submit`. `dataset-actions` is left for 03-25.
- Reusable for the settings dialog: `datasetSchema`, `DatasetFormValues`, `NAME_MAX`, `DESCRIPTION_MAX`, `DESCRIPTION_COUNT_FROM` (`components/create-dataset-dialog/schemas.ts`); `ServerFieldError` (needs a `FormItem` ancestor, set the RHF error with an empty message so `aria-invalid` shows); `datasetErrorTarget(error)` returning `{ target: "name" | "embedding" | "blocked" | "alert", key, text? }`, plus `reasonOf` and `isCancelled` (`pages/datasets/errors.ts`). `embedding_locked` is not mapped yet: add it there.
- Do not stack the shared `AlertDialog` over a `Dialog` (delete confirmation must be a separate dialog opened after the menu closes). A modal dialog needs `onCloseAutoFocus` from its owner to restore focus.
- Query keys: create invalidates `datasetsKeyRoot(tenantId)`; update and delete in 03-25 should also invalidate `datasetQueryKey(tenantId, id)`. Gallery page lives under `["ws", tenantId, "datasets", page, keywords]`.
- Routes and paths: `/datasets` is registered; 03-31 adds `/dataset/files` (read `?id=`; build links with `datasetFilesPath(id)` from `@/constants/app-paths`). Add its route entry after Datasets without a nav entry (or with one, if the spec asks) and update the three nav-order tests only if a nav entry is added.
- Locale prefixes in use: `datasets.*` (documentTitle, title, intro, loading, search, create, created, card.*, visibility.*, missingDefault.*, blocked.*, form.*, field.*, error.*, empty.*, noMatch.*), `errors.dataset.*`, `nav.datasets`. Still to add by 03-25: `datasets.menu.*`, `datasets.card.actions`, `datasets.form.settingsTitle`, `datasets.settings.*`, `datasets.visibility.narrowing`, `datasets.delete.*`, `datasets.deleted`. No key may be both a string and a parent: `datasets.create`, `datasets.created` are strings.

## Self-Check: PASSED

Files present (checked with git status clean after commits) and commits `8d9dd81`, `0db12ff`, `dbf9a91` exist in `git log`.
