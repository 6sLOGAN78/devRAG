---
phase: 04-ingestion-pipeline
plan: 25
subsystem: web
tags: [react-query, polling, workspace-binding, failure-placement, i18n]
requires:
  - phase: 04-24
    provides: Phase 4 services and path builders
  - phase: 04-23
    provides: per-area locale files
provides:
  - "use-document-request: polling documents/detail, usePollHealth, useInvalidateOnParseEnd, parse/switch/settings mutations (onSettled)"
  - "use-chunk-request: chunks list, useChunkRefresh, create/update chunk mutations"
  - "use-ingestion-request: summary, logs, log polling hooks and keys"
  - "use-dataset-binding: shared workspace binding for dataset pages"
  - "pages/dataset/errors: parseFailureOf, cancelFailureOf, switchFailureOf, settingsFailureOf, chunkFailureOf, isTimeout"
  - "constants/failure-codes: failureReasonKey, failureStepKey, failureSentence, isTerminalFailure"
  - "locales/areas/{en,zh}/failures.json"
affects: [04-26, 04-27, 04-28, 04-30, 04-32]
tech-stack:
  added: []
  patterns: [refetchInterval as a function of the query, onSettled refresh, ApiError.kind for timeouts, key-returning pure placement functions]
key-files:
  created:
    - web/src/hooks/use-ingestion-request.ts
    - web/src/hooks/use-chunk-request.ts
    - web/src/hooks/use-chunk-request.test.tsx
    - web/src/hooks/use-dataset-binding.ts
    - web/src/hooks/use-dataset-binding.test.tsx
    - web/src/constants/failure-codes.ts
    - web/src/pages/dataset/errors.test.ts
    - web/src/locales/areas/en/failures.json
    - web/src/locales/areas/zh/failures.json
  modified:
    - web/src/hooks/use-document-request.ts
    - web/src/hooks/use-document-request.test.tsx
    - web/src/pages/dataset/index.tsx
    - web/src/pages/dataset/errors.ts
    - web/src/services/http.ts
    - .planning/DECISIONS.md
key-decisions:
  - "R-180: ApiError.kind, usePollHealth via query timestamps, key families, added locale keys"
requirements-completed: []
duration: ~40min
completed: 2026-10-17
---

# Phase 4 Plan 25: SPA data hooks and failure placement Summary

Polling hooks that keep their place and stop in hidden tabs, mutations that refresh in `onSettled`, one shared `useDatasetBinding`, and pure failure-placement functions with a full `failures` locale area, with no visible UI change.

## Tasks
1. Hooks and binding (RED d29cd06, GREEN c187b9a): `useDocumentsRequest` keeps the previous page and polls 2000 ms only while a row has `run === "1"`; detail, summary, logs and log hooks poll the same way; parse, switch, settings and chunk writes refresh in `onSettled` (documents root, ingestion root, both dataset keys; chunk writes also the chunk root and document detail). The dataset page's binding logic moved verbatim into `useDatasetBinding`; the dataset page tests pass unchanged.
2. Failure placement (RED separate commit, GREEN 0536b92): table-tested pure functions; code and step maps including `too_many_chunks`; `failures` area files in en and zh.

## Verification
- Web unit project: 66 files, 1273 tests pass; `tsc --noEmit` exits 0; `package.json` and lockfile unchanged.
- `check_decisions.py` passes (180 rows).

## Deviations from Plan
- **[Rule 3 - Blocking] `ApiError.kind`:** the plan wants timeouts recognised "by status or error kind", but the response interceptor produced status 0 with only a translated message for both timeout and network. Added an optional `kind` field in `services/http.ts` (not in the plan's file list).
- **[Plan vs note] `confirmCountsOf`:** per the 04-24 note it stays in `document-service.ts`; `errors.ts` re-exports it. It returns `[]` (not `null`) for any other answer.
- **[Rule 3] Copy scan:** the literal type `"document"` in `errors.ts` tripped the no-hardcoded-copy scan; the `SettingsMode` type lives in `constants/failure-codes.ts`.
- **[Rule 2] Extra keys** for Checker Flags 3, 4, 5, 8: `datasets.parse.error.limited`, `datasets.chunking.error.datasetGone`, `datasets.chunking.storedUnavailableDataset`, `datasets.details.reason.queue` / `.documentGone`, `inspector.editor.refused.unreachable` / `.dimension` / `.documentGone` (R-180).
- **[Process]** `useDatasetBinding` was written before its test was run, so its tests passed on first run; the RED commits cover the document, chunk and error tests only.
- Assumption: a running log row has `result === "running"` (matches `LOG_RUNNING` in `common/ingest_codes.py`).

## Notes
- The Chinese strings in `failures.json` are drafts for the B-18 review.
- `useDatasetBinding` returns `{ dataset, state, bound, unbindable, error, refetch }`; `bound` is true only once the store is initialised and the active workspace is the dataset's. Other dataset pages must gate their requests on it.
- The pages that consume `usePollHealth` and the failure functions arrive in later plans (04-26 onward).

## Known Stubs
None.

## Threat Flags
None.

## Self-Check: PASSED
