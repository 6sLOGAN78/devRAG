---
phase: 04-ingestion-pipeline
plan: 05
subsystem: ui
tags: [react, a11y, native-controls, permissions, sidebar]
requires:
  - phase: 03-datasets
    provides: ChoiceGroup, Sheet, canRemoveDocument, app-sidebar isNavActive
provides:
  - Switch, Checkbox, SegmentedControl native-element parts
  - ChoiceGroup per-option disabled and badge
  - SheetContent side="right" with closeLabel
  - canChangeDocument / useCanChangeDocument
  - Sidebar keeps Datasets active on /chunk and /document
affects: [04-ingestion-pipeline page plans]
tech-stack:
  added: []
  patterns: [hand-written native controls, words beside colour, parts hold no copy]
key-files:
  created:
    - web/src/components/ui/switch.tsx
    - web/src/components/ui/checkbox.tsx
    - web/src/components/ui/segmented-control.tsx
    - web/src/hooks/use-dataset-permissions.test.ts
  modified:
    - web/src/components/ui/choice-group.tsx
    - web/src/components/ui/sheet.tsx
    - web/src/components/ui/ui-parts.test.tsx
    - web/src/hooks/use-dataset-permissions.ts
    - web/src/components/app-sidebar.tsx
    - web/src/components/shell-i18n.test.tsx
decisions:
  - canChangeDocument delegates to canRemoveDocument (one rule, two names)
  - Sidebar exact-or-slash nested paths held in NESTED_PATHS, separate from prefix entries
metrics:
  tasks: 2
  files: 10
  completed: 2026-10-17
---

# Phase 4 Plan 05: Native controls and document permission helper Summary

Native Switch, Checkbox and SegmentedControl, ChoiceGroup disabled/badge options, a right-hand Sheet variant, and `canChangeDocument` sharing the delete rule, with no new npm package.

## Tasks

| Task | Commit |
|------|--------|
| 1. Switch, Checkbox, SegmentedControl, ChoiceGroup options, Sheet side | b166102 |
| 2. canChangeDocument and sidebar nested paths | c5ffae3 |

## Verification

`npx vitest run src/hooks src/components src/layouts`: 17 files, 292 tests pass. `tsc --noEmit` clean. `web/package.json`, `package-lock.json` and `constants/routes.ts` unchanged.

## Deviations from Plan

- Test for the default Sheet close label expects "Close" (the actual `nav.closeMenu` English value), not "Close menu".
- RED step was observed as a failing import of the new parts (test file could not load) rather than per-test assertion failures; tests were written before the parts.

## Known Stubs

None.

## Threat Flags

None.

## Self-Check: PASSED
