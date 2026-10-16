---
phase: 04-ingestion-pipeline
plan: 23
subsystem: web
tags: [i18n, locales, test-server, vite-glob]
requires:
  - phase: 04-05
    provides: Phase 3 locale files and dataset test server
provides:
  - "@/locales: mergeTrees, en, zh, AREAS (merged per-area string trees)"
  - "test server seam: server.use, server.areaState, AreaHandler/AreaContext, glob-discovered server-areas modules"
affects: [phase 4 web plans]
tech-stack:
  added: []
  patterns: [import.meta.glob eager discovery, duplicate-key load error, per-server area state]
key-files:
  created:
    - web/src/locales/index.ts
    - web/src/locales/areas.test.ts
    - web/src/test/server-areas.test.ts
  modified:
    - web/src/i18n/index.ts
    - web/src/locales/locales.test.ts
    - web/src/constants/no-hardcoded-copy.test.ts
    - web/src/components/shell-i18n.test.tsx
    - web/src/pages/user-setting/model/errors.test.ts
    - web/src/test/dataset-server.ts
key-decisions:
  - "en/zh are typed Tree & typeof base JSON so existing typed access (zh.errorState.defaultNoun) still compiles"
  - "AREAS also exposes the per-file trees (AREAS.trees) so the generic parity test checks each area pair"
requirements-completed: []
duration: ~10min
completed: 2026-10-17
---

# Phase 4 Plan 23: Per-area locales and test-server handlers Summary

The SPA now reads one merged string tree per language (Phase 3 base plus `locales/areas/{en,zh}/*.json`), and the in-memory test server accepts glob-discovered handler modules, so later web plans own disjoint files.

## Tasks
1. Merged locale trees (commit 5c9d921). `areas.test.ts` failed first (no module), then passed. A duplicate key throws naming the dotted key and file. The five consumers import from `@/locales`. Generic per-area parity (same file names, keys, placeholders, no empties, no base redefinition) runs without edits to shared tests.
2. Test server areas (commit adb5b9a). `use`, `areaState`, `reset` clearing state, handlers running after holds and forced failures and before core routes. `ok` and `failure` exported. A module without `handle` throws naming the file. 7 new tests.

## Verification
- Web unit project: 59 files, 1166 tests pass. `tsc --noEmit` exits 0.
- `package.json` and `package-lock.json` unchanged; `en.json` and `zh.json` untouched.
- grep for `locales/en.json|zh.json` outside `index.ts` and `areas.test.ts` is empty.

## Deviations from Plan
None in behavior. `locales.test.ts` now imports `Tree` from `@/locales` instead of declaring it. No area files or `server-areas` directory were created, as specified.

## Notes
- The `live` vitest project needs the full stack and was not run; it fails here without it.
- `areas.test.ts` imports `locales.test.ts` for `diffLocales`, so the parity describe blocks also run inside that file (harmless duplication).

## Self-Check: PASSED
