---
phase: 03-models-knowledge-bases-and-upload
plan: 23
subsystem: ui
tags: [ui-parts, pagination, search-input, choice-group, textarea, dataset-service, workspace-scoped, react-query]

requires:
  - phase: 03-models-knowledge-bases-and-upload
    provides: "03-14 dataset create, list and open routes; 03-18 update and delete; 03-20 service and hook patterns; 03-03 workspace store"
provides:
  - web/src/components/ui/{textarea,pagination,search-input,choice-group}.tsx
  - web/src/services/dataset-service.ts (listDatasets, getDataset, createDataset, DatasetView, DatasetDetailView, UploadLimitsView)
  - web/src/hooks/use-knowledge-request.ts (datasetsKeyRoot, datasetsQueryKey, datasetQueryKey, useDatasetsRequest, useDatasetRequest, useCreateDatasetRequest)
  - api-paths.ts (datasetsPath, datasetPath, datasetDocumentsPath, documentUploadPath)
affects: [03-24 upload dialog, 03-25 dataset page, 03-30 gallery and create dialog, 03-31 live journey]

tech-stack:
  added: []
  patterns:
    - "UI parts hold no copy: every label and the formatted status text arrive as props"
    - "Dataset keys are [\"ws\", tenantId, \"datasets\"|\"dataset\", ...]; create invalidates the tenant's datasets root only"
    - "Service clamps page, page_size and keywords before the request and omits an empty keywords parameter"

key-files:
  created:
    - web/src/components/ui/textarea.tsx
    - web/src/components/ui/pagination.tsx
    - web/src/components/ui/search-input.tsx
    - web/src/components/ui/choice-group.tsx
    - web/src/components/ui/ui-parts.test.tsx
    - web/src/services/dataset-service.ts
    - web/src/services/dataset-service.test.ts
    - web/src/hooks/use-knowledge-request.ts
    - web/src/hooks/use-knowledge-request.test.tsx
  modified:
    - web/src/constants/api-paths.ts

key-decisions:
  - "Pagination uses aria-disabled (not disabled) on the edge buttons and ignores their clicks, so focus is not lost at the last page"
  - "createDataset leaves out fields the caller did not choose, so the server applies the workspace default embedding model"
  - "createDataset returns the list-shaped DatasetView; the detail shape (with upload_limits) is for getDataset"

patterns-established:
  - "SearchInput cancels its debounce timer on clear and unmount; clear calls onSearch('') at once"

requirements-completed: [UI-10, KB-01, KB-02, KB-04, TEN-13]

duration: 12min
completed: 2026-10-09
---

# Phase 3 Plan 23: List and Form Parts and the Dataset Data Layer Summary

**Four hand-written UI parts (Textarea, Pagination, SearchInput with a 300 ms debounce, ChoiceGroup) plus a clamped, explicit-mapper dataset service and workspace-keyed React Query hooks, with no new package.**

## Performance

- **Tasks:** 3 of 3
- **Files:** 9 created, 1 modified

## Accomplishments

- Parts and data layer are covered by 15 UI-part tests, 9 service tests and 9 hook tests (33 in total).
- Two-workspace hook test proves a workspace switch issues a second request with the new `tenant_id` and never serves the first workspace's data.
- Create invalidation test proves only the active tenant's list keys are invalidated.

## Task Commits

1. **Task 1: failing tests (red)** - `5b59e6b`. Red run: all three files failed with `Failed to resolve import "./choice-group"`, `./dataset-service`, `./use-knowledge-request` (no tests ran).
2. **Task 2: UI parts** - `c29772f` (15 passed)
3. **Task 3: paths, service, hooks** - `cbe7053`

## Verification

- `npm run test -- --run`: Test Files 44 passed (44), Tests 840 passed (840). The `chunk failed` / `shell failed` stderr lines are existing route-error tests logging expected errors.
- `npm run typecheck`: exit 0. `npm run build`: exit 0 (existing chunk-size notice only).
- `git diff --stat -- web/package.json web/package-lock.json`: empty.
- grep: no `font-medium` or `dangerouslySetInnerHTML` in the new parts.

## Deviations from Plan

None in behaviour. Notes:

- One expectation in my own `dataset-service.test.ts` (a numeric `permission` expected to coerce to an empty string) contradicted the stated coercion rule ("strings and numbers coerced"); the fixture was changed to a non-scalar object. Behaviour was not weakened.
- The red commit contains test files that do not typecheck until Task 2 and 3 land (they parse and fail on imports, as the plan requires).

## API facts checked against code

Verified against `api/apps/restful_apis/dataset_api.py` and `api/utils/reasons.py`:
- Dataset `id` is a string (not an integer); `description` and `avatar` are non-null strings in the DTO. Delete `ids` is `list[str]` with the count check in the service (`ids_invalid`).
- `page_size` 1..100 (default 12), `keywords` max 128, `tenant_id` must match `^[0-9a-f]{32}$` (the web tests use short ids like `t1` only because the adapter is a stub).
- Reasons `duplicate_name`, `embedding_locked`, `dataset_invalid`, `no_default_embedding`, `dimension_unsupported`, `index_unavailable`, `busy`, `ids_invalid` exist in `reasons.py`. The HTTP codes were not re-checked per handler here; 03-30 should read `data.reason` and the status from `ApiError` rather than assume codes.

## Notes for later plans

- **Pagination**: `<Pagination page pages onPageChange previousLabel nextLabel statusLabel />`; the caller computes `pages = ceil(total / 12)` and `statusLabel` from `common.pagination.status`. Renders nothing for `pages <= 1`.
- **SearchInput**: `<SearchInput value onSearch label clearLabel debounceMs? id? className? />`; `value` re-syncs the field when the parent changes it; the parent resets `page` to 1 inside `onSearch`.
- **ChoiceGroup**: `<ChoiceGroup legend name value onChange options={[{value,title,description}]} disabled? />`. Dataset visibility values are `me` and `team`.
- **Textarea**: `<Textarea />` is a forwardRef textarea (works with react-hook-form `register`).
- **Service**: `listDatasets({tenantId,page,pageSize,keywords}) -> {items,total}`; `getDataset(id) -> DatasetDetailView` (with `uploadLimits: {maxFileBytes,maxFilesPerRequest,maxDocuments,allowedExtensions} | null`); `createDataset({tenantId,name,description?,embdId?,permission?}) -> DatasetView` (30 s timeout, silent). There is no `updateDataset`/`deleteDatasets` yet (03-18 routes exist; 03-25 adds the service calls).
- **Hooks**: `DATASETS_PAGE_SIZE = 12`; `useDatasetsRequest({page,keywords})`, `useDatasetRequest(id | undefined)` (idle without id), `useCreateDatasetRequest()` takes `CreateDatasetInput` including `tenantId` (take it from `useActiveWorkspace()?.tenantId`).
- **Query keys**: `datasetsKeyRoot(t) = ["ws", t, "datasets"]`, `datasetsQueryKey(t, page, keywords) = [..., page, keywords]`, `datasetQueryKey(t, id) = ["ws", t, "dataset", id]`. Detail key is not under the list root, so a create does not refetch open datasets; update/delete mutations in 03-25 should invalidate both.
- **Paths**: `datasetsPath`, `datasetPath(id)`, `datasetDocumentsPath(id)`, `documentUploadPath` in `constants/api-paths.ts`.
- Locale keys for the gallery and dialog (including `common.pagination.*`) are not added here; 03-30 owns them.

## Known Stubs

None.

## Threat Flags

None.

## Self-Check: PASSED

Files and commits `5b59e6b`, `c29772f`, `cbe7053` exist.
