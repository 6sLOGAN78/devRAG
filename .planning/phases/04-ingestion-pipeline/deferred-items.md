# Deferred items (phase 04)

## test/testcases/test_phase3_isolation.py guard tests fail (found in plan 04-18)

RESOLVED in d13ec02: invokers added for the seven Phase 4 rows; the guard tests and the full isolation table pass.
- web/src/pages/dataset/ingestion-summary.test.tsx:87 trips the no_sleep gate (plan 04-26, found during 04-33; out of scope) — RESOLVED: the fixed wait is replaced by a waitUntil negative check (no new summary poll within 2.6 s).
