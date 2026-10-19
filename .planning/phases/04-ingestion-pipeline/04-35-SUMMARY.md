---
phase: 04-ingestion-pipeline
plan: 35
subsystem: testing
tags: [traceability, source-gate, memory, records, clean-room]
requires:
  - phase: 04-34
    provides: live and real-Chrome journeys
provides:
  - "test_phase4_traceability.py: 60 requirement ids, D-01..D-31, registry rows, summaries (PHASE4_GATE=1)"
  - "phase4-source-gate.test.ts: forbidden packages and markup, test-tree imports (T-04-23-03)"
  - "test_executor_memory.py: measured executor peak; limit 384m"
  - "decision rows R-188..R-191, blockers B-34..B-36, 04-HUMAN-UAT.md"
affects: []
key-files:
  created:
    - test/unit_test/test_phase4_traceability.py
    - test/integration/test_executor_memory.py
    - web/src/constants/phase4-source-gate.test.ts
    - .planning/phases/04-ingestion-pipeline/04-HUMAN-UAT.md
    - .planning/phases/04-ingestion-pipeline/04-35-GATE-LOG.md
  modified:
    - docker/docker-compose.dev.yml
    - test/unit_test/test_compose_files.py
    - test/unit_test/test_phase4_records.py
    - .planning/DECISIONS.md
    - .planning/BLOCKERS.md
    - .planning/phases/04-ingestion-pipeline/04-VALIDATION.md
key-decisions:
  - "R-188: executor limit 768m to 384m from a measured peak of 201 MiB"
requirements-completed: []
status: complete-with-deferred-gate
completed: 2026-10-19
---

# Phase 4 Plan 35: Traceability, memory and exit gate Summary

Tasks 1 and 2 are done and committed. Task 3 (three clean-room runs) is **deferred by the user** on 2026-10-19. The original project-guard refusal was resolved. Later attempts found and fixed two out-of-date tests and one real roll-up atomicity bug (`d65664e`, `2925739`, `4d651f6`), and hardened one live test (`ed9e383`). Every tier has passed on its own, but three full runs have not. See `04-DEFERRED-CLEAN-ROOM.md`.

## Tasks

1. **Traceability, source gate, records** (7d97b35). Traceability test (60 ids, 31 decisions, 9 route markers, at least 31 plans; summaries only with `PHASE4_GATE=1`, which passes). Source gate also fails on `@/test`, `src/test`, `./test/`, `../test/` imports in non-test files. Records test now covers R-154..R-191 with one title per decision. Rows R-188 (memory), R-189 (PDF page cap 20,000, an unreviewed agent choice), R-190 (PDF chunk boxes as coarse as the block, known limitation), R-191 (`elastic_transport`, `urllib3`, `httpx`, `httpcore` at WARNING). B-34, B-35 and `04-HUMAN-UAT.md` (box alignment screenshots, Chinese copy review, page cap). The decisions the executors reported earlier were already rows R-168..R-187.
2. **Executor memory** (2f642d0). 13-page PDF, 40-paragraph TXT, DOCX, XLSX, PPTX and HTML parsed one by one and in pairs through the real executor. Peak 127 MiB sampled and 193 MiB cgroup mark at 768m; after recreating the executor at 384m, 161 and 201 MiB, `OOMKilled` false, 201 is under 60 percent of 384. Limit set to 384m in the dev override and the compose test. Stack total 2078 MiB of the 3891 MiB budget; container limits sum to 4576 MiB; host available RAM 7743 MiB.
3. **Exit gate** (12de772, log only). Pre-gate checks passed (7 of 7 CI gates, 2055 unit, 1703 web unit). `clean_room.sh --runs 3` stopped at `project-guard` before touching anything. Fix needed from the user is in `04-35-GATE-LOG.md` and B-36.

## Verification

- `uv run python run_tests.py -m unit`: 2055 passed, 4 skipped. Web unit: 82 files, 1703 tests. `scripts/ci/run_all.py`: 7 of 7. `check_decisions.py`: 191 rows OK. `PHASE4_GATE=1` traceability: 6 passed.
- `git diff --stat 6ab0cc9~1 HEAD -- web/package.json web/package-lock.json` is empty. Python packages changed in 04-02 (user-approved).

## Deviations from Plan

- Peak is the larger of the sampled `docker stats` value and the cgroup high-water mark, because one sample takes about two seconds; the plan named only sampling.
- Requirements not ticked and `04-VALIDATION.md` not approved: both depend on the clean-room gate. No Partial requirement was touched.
- The ROADMAP plan 04-35 box is unticked and the phase status stays In Progress.

## Known Stubs

None.

## Threat Flags

None. The gate log contains no key material (`grep -c 'sk-'` prints 0).

## Self-Check: PASSED

Commits 2f642d0, 7d97b35 and 12de772 exist; the created files exist. The plan's outcome (three clean-room runs) is NOT achieved.
