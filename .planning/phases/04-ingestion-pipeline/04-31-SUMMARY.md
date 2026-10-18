---
phase: 04-ingestion-pipeline
plan: 31
subsystem: web
tags: [react, chunk-editor, unsaved-changes, react-router, useBlocker, i18n]
requires:
  - phase: 04-30
    provides: chunk inspector page, ChunkCard, ChunkList, chunks test-server area
  - phase: 04-25
    provides: chunkFailureOf table and the refusal locale keys in failures.json
  - phase: 04-18
    provides: embed-before-write chunk POST and PATCH
provides:
  - "ChunkEditor: inline edit and add editor with rules, pending, success and refusals that keep the typed text"
  - "DiscardChangesDialog and useEditGuard: held actions, route blocker, beforeunload"
  - "Edit pencil, Add chunk, add-flow ending and Add a chunk by hand in the inspector"
  - "Test-server area chunk-edit.ts: embed-before-write POST and PATCH with injectable refusals"
affects: [04-32]
tech-stack:
  added: []
  patterns: [editor state held by the page as a snapshot of the chunk, dirty flag read from a ref by the router blocker, held action cleared by its owner]
key-files:
  created:
    - web/src/pages/chunk/chunk-editor.tsx
    - web/src/pages/chunk/discard-dialog.tsx
    - web/src/pages/chunk/use-edit-guard.ts
    - web/src/pages/chunk/chunk-editor.test.tsx
    - web/src/test/server-areas/chunk-edit.ts
    - web/src/locales/areas/en/editor.json
    - web/src/locales/areas/zh/editor.json
  modified:
    - web/src/pages/chunk/chunk-card.tsx
    - web/src/pages/chunk/chunk-list.tsx
    - web/src/pages/chunk/index.tsx
    - web/src/pages/chunk/inspector-states.tsx
    - web/src/pages/chunk/chunk-inspector.test.tsx
    - web/src/pages/chunk/chunk-list.test.tsx
    - .planning/DECISIONS.md
key-decisions:
  - "R-186: Editing snapshot held by the page, orphan card keeps the editor on a 404, blocker only on pathname or id/doc change, other leaving actions guarded as actions, provider sentence truncated to 300 characters"
requirements-completed: []
duration: ~1h15
completed: 2026-10-19
---

# Phase 4 Plan 31: Chunk editor and unsaved-changes guard Summary

A member who may change a document can correct a chunk's text or add a chunk by hand inside the inspector: a write is accepted only when the new text could be embedded, a refusal names its reason and keeps the typed text, and nothing typed is lost without the Discard dialog, the router blocker or the browser's own unload prompt.

## Tasks

1. **ChunkEditor, DiscardChangesDialog, useEditGuard, test-server area** (RED 9e50ec0, GREEN 278ac44). The editor has a labelled textarea (focus at the end for an edit), helper text, `onTouched` validation (required after trimming, 32,000 characters), a primary that is `aria-disabled` until the text differs and is valid, Ctrl/Cmd+Enter, Esc through the guard, a pending state (busy button, read-only textarea, `role="status"` line, an in-flight ref that ignores a second submit), success toasts and a destructive `Alert` per refusal that takes focus, shows the reason from `chunkFailureOf`, the bounded provider sentence as a text node and, for an edit, 'The text in the search index is unchanged.'. The dialog is a standalone `AlertDialog` with "Keep editing" focused first and no overlay close. `useEditGuard(dirty)` returns `guard`, `pending`, `confirm`, `cancel` and `release`. The `chunk-edit` area embeds before it writes, so a refusal leaves the stored row untouched.
2. **Page integration** (RED 2895ff5, GREEN 4489edb). `ChunkCard` takes `onEdit` and `editor` (the editor replaces the text; the switch and the pencil are not drawn while it is there). `ChunkList` draws the pencil and the toolbar 'Add chunk' for callers who may change a parsing-idle document, the add card at the top, and returns focus to the control that opened the editor. `InspectorBody` owns the one `Editing` state, wraps page, search, filter and clear in the guard, shows the Discard dialog, and after an add clears `keywords` and `show`, goes to the last page, selects the new chunk and focuses its header. `DocumentEmpty` gains 'Add a chunk by hand' for never-parsed and unparseable documents; pressing it shows the list column with the add editor.

## Verification

- `npx vitest run --project unit`: 78 files, 1651 tests pass (editor 42, inspector page 63 including 31 new, list 25, states 16).
- `npx tsc --noEmit` exits 0; `npm run build` exits 0; `git diff --stat -- web/package.json web/package-lock.json` is empty.
- `uv run python scripts/ci/run_all.py`: 7/7 gates pass (decisions 186 rows, no_sleep).
- The seven guarded actions are a table run twice (clean: runs at once; changed: dialog first, action after Discard changes). Selecting a chunk, paging the preview and zooming open no dialog. `beforeunload` is prevented only while the text is changed.
- The live-stack vitest project was not run.

## Deviations from Plan

### Auto-fixed Issues

None. Two implementation points differ from a literal reading of the plan and are recorded in R-186:

- **[Rule 2 - correctness] 404 on an edit.** The mutation's awaited `onSettled` refetch removes the vanished chunk from the list, which would have unmounted the editor and its alert and lost the typed text. The page keeps a snapshot of the chunk it opened, and `ChunkList` draws that card with the editor at the top while the chunk is not listed. 'Refetch on dismiss' is therefore met by the settled refetch.
- **Blocker scope.** `useBlocker` blocks a change of pathname or of `id`/`doc` only; page, search and filter changes are held as actions (the plan's own list), so the list's past-the-end page step is never held by a dialog.

### Other differences

- **Provider sentence over 300 characters** is shown cut to 300 (the existing `chunkFailureOf` contract of plan 04-25, covered by its tests), not replaced by the fixed line as the behaviour list words it. An empty or blank sentence shows only the fixed line.
- **Touched rule.** The over-length message shows as soon as the text is over 32,000 characters, not only after blur, because a pasted text would otherwise leave a disabled button without a visible reason.
- **Search box.** After 'Keep editing' on a held search, the shared `SearchInput` still shows the typed words while the address and the list are unchanged.
- **Files outside the plan's list:** `chunk-list.test.tsx` (the host passes the new props), `DECISIONS.md` (R-186). `use-edit-guard.ts` also returns `release()`, which the plan did not list.
- **TDD order.** RED commits hold only tests and test infrastructure; the first RED fails on the missing modules.

## Known Stubs

None.

## Threat Flags

None. Hostile provider text and chunk text render as text nodes (T-04-31-01, tested); controls follow `useCanChangeDocument` and hide while parsing, 403 and 409 are handled (T-04-31-02); the guard, blocker and `beforeunload` cover every leaving action (T-04-31-03); one editor is mounted per chunk (T-04-31-04); an in-flight ref ignores a second submit (T-04-31-05).

## Notes for later plans

- 04-32: the page owns `Editing`, the dirty flag and the guard in `InspectorBody`; `ChunkList` takes the editor props. Requirements were not ticked, per the orchestrator. Chinese strings in `editor.json` are drafts for the B-18 review.

## Self-Check: PASSED

- Commits 9e50ec0, 278ac44, 2895ff5 and 4489edb exist; all created files exist; full unit suite, type check, build and the 7 CI gates are green.
