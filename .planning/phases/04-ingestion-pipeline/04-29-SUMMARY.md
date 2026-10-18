---
phase: 04-ingestion-pipeline
plan: 29
subsystem: web
tags: [react, dialog, react-hook-form, zod, chunking, parser-config, i18n]
requires:
  - phase: 04-28
    provides: DatasetFiles-owned sheet pattern, focus return to the opener
  - phase: 04-26
    provides: row overflow menu, files test-server area, files harness
  - phase: 04-25
    provides: settingsFailureOf, storedUnavailableKey, document detail and settings hooks
  - phase: 04-24
    provides: updateDocumentSettings, updateDatasetChunking services
provides:
  - "ChunkMethodDialog: one Dialog for a document and the dataset default; eight methods, seven disabled with a badge"
  - "ParseConfiguration: chunk size, delimiters (typed as \\n and \\t), overlap, plus read-only 'Not available yet' rows"
  - "Row menu item 'Chunking method' and dataset menu item 'Default chunking method'"
  - "constants/chunk-methods.ts and SETTINGS_MODES; useUpdateDatasetChunkingRequest; test area document-settings.ts"
affects: [04-30, 04-32]
tech-stack:
  added: []
  patterns: [raw zod resolver with a second parse on submit, dialog body keyed by target, owner-supplied onCloseAutoFocus]
key-files:
  created:
    - web/src/components/chunk-method-dialog/index.tsx
    - web/src/components/chunk-method-dialog/chunk-method-form.tsx
    - web/src/components/chunk-method-dialog/chunk-method-dialog.test.tsx
    - web/src/components/parse-configuration/index.tsx
    - web/src/components/parse-configuration/schema.ts
    - web/src/components/parse-configuration/delimiters.ts
    - web/src/components/parse-configuration/parse-configuration.test.tsx
    - web/src/constants/chunk-methods.ts
    - web/src/test/server-areas/document-settings.ts
    - web/src/locales/areas/en/chunking.json
    - web/src/locales/areas/zh/chunking.json
  modified:
    - web/src/components/dataset-actions-menu.tsx
    - web/src/components/ui/choice-group.tsx
    - web/src/constants/failure-codes.ts
    - web/src/hooks/use-knowledge-request.ts
    - web/src/pages/dataset/dataset-files.tsx
    - web/src/pages/dataset/dataset-workspace.tsx
    - web/src/pages/dataset/document-row.tsx
    - web/src/pages/dataset/document-row-actions.tsx
    - web/src/pages/dataset/errors.ts
    - web/src/services/dataset-service.ts
    - web/src/test/server-areas/files.ts
    - web/src/pages/dataset/dataset-workspace.test.tsx
    - web/src/components/file-upload-dialog/upload-dialog.test.tsx
    - web/src/pages/dataset/settings-dialog.test.tsx
    - .planning/DECISIONS.md
key-decisions:
  - "R-184: raw zod resolver plus a second parse on submit; mode literals in SETTINGS_MODES; English title 'Tables' instead of 'Table' (copy-scan collision); Save stays clickable when dirty but invalid so range messages can show"
requirements-completed: []
duration: ~1h30
completed: 2026-10-19
---

# Phase 4 Plan 29: Chunking method dialog and parser configurator Summary

Members who may change a document can now set its chunk size (1 to 8192), delimiters (typed as `\n` and `\t`, 1 to 64 characters) and overlap (0 to 50) in a dialog, and managers can set the same as the dataset default; all eight methods are listed, but only General can be chosen or sent, and layout recognition and auto-keywords appear as read-only "Not available yet" text.

## Tasks

1. **Delimiter conversion, schema and ParseConfiguration** (RED 14e4539, GREEN 86072d4). `toEscaped`/`fromEscaped` round-trip 200 random strings. The zod schema mirrors the server's `ParserConfig` ranges with locale-key messages. `ParseConfiguration` renders the three fields (Mono delimiter input, helpers) and a "Not available yet" group asserted to contain no input, select, textarea or button.
2. **Dialog, two modes and menu entries** (RED 256e3b2, GREEN 2cfb308). Document mode prefills from the document detail; dataset mode from the dataset detail. Only changed keys are sent. A stored unbuilt method selects no radio and shows the info alert (document or dataset wording); a parsed document shows the "chunks stay as they are" note; errors are placed by status and reason (`chunker_unavailable` under Method, `parser_config_invalid` under the field named in `data.field`, 403, 404, 409 `parse_running`, fallback). Body mounted only while open and keyed by target (FE-04); Esc and outside click blocked while saving; focus returns to the row's menu button or the dataset menu button. Menu items: "Chunking method" (not for parsing rows or read-only callers) and "Default chunking method" (managers only, above "Dataset settings").

## Verification

- `npx vitest run --project unit`: 73 files, 1472 tests pass (dialog suite 33 tests, configurator suite 19, one new workspace wiring test).
- `npx tsc --noEmit` exits 0; `npm run build` exits 0; `git diff --stat -- web/package.json web/package-lock.json` is empty.
- `uv run python scripts/ci/run_all.py`: 7/7 gates pass.
- `grep -rn '"naive"\|"qa"\|"paper"' web/src/components web/src/pages web/src/layouts` now prints only a `"qa"` constant in the dialog test (see Deviations).
- The live-stack vitest project was not run.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed zod resolver cannot type a transformed output.** `useForm<Input, unknown, Output>` with `zodResolver(schema)` failed type-checking. The form uses `zodResolver(..., { raw: true })` and parses again on submit, so the delimiter is converted exactly once. Commit 86072d4.

**2. [Rule 3 - Blocking] Copy scan collisions.** The English method title "Table" equals a literal in `ui/table.tsx`, so the title is "Tables" (the plan says to change wording, not the gate). The mode literal `"document"` also equals a locale value, so the modes live in `SETTINGS_MODES` in `constants/failure-codes.ts`. Commit 2cfb308.

**3. [Rule 2 - Missing functionality] Dirty but invalid form could never show its range messages.** With mode `onSubmit` and a button that is `aria-disabled` and `pointer-events-none`, an out-of-range number gave no feedback. The button stays aria-disabled but clickable once something changed, so a click validates. Commit 2cfb308.

### Other differences

- **TDD order.** Implementation was written before the tests in both tasks; the RED commits were produced by moving the implementation files aside, confirming the suites fail on the missing modules, and committing the tests alone.
- **Files outside the plan's list:** `choice-group.tsx` (`help`, per-option `testId`), `failure-codes.ts` (`SETTINGS_MODES`), `dataset-service.ts` (`updateDatasetChunking` takes a partial), `errors.ts` (`invalidFieldOf`), `document-row.tsx`, `files.ts` (document and dataset chunking values), `dataset-workspace.test.tsx`, `DECISIONS.md` (R-184), and two earlier tests that used `"naive"` as a literal.
- **Acceptance grep.** The dialog test keeps `SERVER_METHOD = "qa"` as a literal on purpose (a server value for the stored-unbuilt case); production code, `layouts` and the other tests are clean.
- **Dataset-mode loading** reuses `useDatasetRequest`, so the dataset detail query is shared with the workspace and usually already cached.

## Known Stubs

None. The two "Not available yet" rows are the intentional read-only text required by D-27; UI-14 is delivered in part and Phase 6 completes it.

## Threat Flags

None. Ranges equal the server's (T-04-29-01); unbuilt methods are disabled radios and are never sent (T-04-29-02); menu items follow `useCanChangeDocument` and `useCanManageDataset`, and a 403 shows the lost-permission alert (T-04-29-03); the body is keyed by target id (T-04-29-04). Delimiters are plain strings and never compiled as patterns.

## Notes for later plans

- Chinese strings in `chunking.json` are drafts for the B-18 review.
- UI-14 stays Partial; requirements were not ticked, per the orchestrator.
- `ChunkMethodDialog` takes `target`, `open`, `onOpenChange`, `onCloseAutoFocus`; the chunk inspector (04-30) can open it for a document with `SETTINGS_MODES.document`.

## Self-Check: PASSED

- Commits 14e4539, 86072d4, 256e3b2 and 2cfb308 exist; all created files exist; full unit suite, type check, build and the 7 CI gates are green.
