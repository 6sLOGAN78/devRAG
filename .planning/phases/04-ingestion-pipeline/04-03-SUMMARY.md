---
phase: 04-ingestion-pipeline
plan: 03
subsystem: configuration
tags: [settings, constants, reasons, env-catalogue]
requires: []
provides:
  - Settings.ingest (IngestSettings) with bounded values and a reclaim/TTL consistency check
  - common/ingest_codes.py (run codes, steps, failure and terminal codes, method ids, IMPLEMENTED_PARSERS)
  - nine new reason strings in api/utils/reasons.py
affects: [all later Phase 4 plans]
key-files:
  created: [common/ingest_codes.py, test/unit_test/test_ingest_settings.py, test/unit_test/test_ingest_codes.py]
  modified: [common/settings.py, conf/service_conf.yaml.template, docker/.env.example, docker/docker-compose.yml, api/utils/reasons.py, test/unit_test/test_env_catalog.py, test/unit_test/test_rate_limit_config.py]
decisions:
  - "too_many_chunks (R-155) is included in FAILURE_CODES and TERMINAL_CODES"
metrics:
  tasks: 2
  files: 10
  completed: 2026-10-17
---

# Phase 4 Plan 03: Ingest settings and shared constants Summary

`IngestSettings` (23 bounded fields, retry cap `INGEST_MAX_ATTEMPTS` flows env -> template -> compose -> settings), a pure `common/ingest_codes.py` vocabulary module, and nine new API reasons.

## Tasks

| Task | Commit | Notes |
|------|--------|-------|
| 1 IngestSettings, template, env catalogue, compose | f61ef81 | RED seen (ImportError) before implementation |
| 2 Constants module and reasons | 32413b2 | RED seen (collection error) before implementation |
| Fix to existing test | df10286 | see deviations |

## Deviations from Plan

**1. [Rule 1 - Bug] Dev-overlay leak check matched a substring**
- **Found during:** full unit run after Task 2
- **Issue:** `test_dev_overlay_values_do_not_appear_in_production_compose` asserted `"100000" not in text`; the new default `XLSX_MAX_CELLS=1000000` contains that substring.
- **Fix:** the check now matches the whole number with a regex, keeping its intent.
- **Files modified:** test/unit_test/test_rate_limit_config.py
- **Commit:** df10286

**2. [Rule 2 - Completeness] `too_many_chunks` added to failure and terminal codes**, because R-155 defines it as a hard terminal error.

## Known Stubs

None.

## Verification

Full unit suite: 1747 passed, 3 skipped. `scripts/ci/run_all.py`: 7/7 gates passed. `docker/docker-compose.dev.yml` untouched.

## Self-Check: PASSED
