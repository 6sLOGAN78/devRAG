---
phase: 05-retrieval-and-cited-chat-core-value-gate
plan: 02
subsystem: retrieval
tags: [fusion, rrf, query-builder, synonyms, settings, valkey]
requires:
  - phase: 05-01
    provides: "decision rows R-192..R-202 and the REQUIRED_TITLES records test"
provides:
  - "rag/nlp/fusion.py: fuse, cosine_from_es_score, token_overlap, rank_feature, rrf, apply_threshold, paginate, sanitize_floats"
  - "rag/nlp/query.py: QueryBuilder, QueryPlan, FIELDS (seven boosted fields), STOPWORDS"
  - "rag/nlp/synonym.py: SynonymSource (dictionary plus fail-open Valkey cache), load_dictionary"
  - "RetrievalSettings (Settings.retrieval) and RETRIEVAL_* env names; decision row R-203"
affects: [05-03, 05-04, 05-11, 05-24]
tech-stack:
  added: []
  patterns: ["golden-number tests with a locally built swapped formula", "per-batch Valkey client, closed in finally, cache fails open to an in-repo dictionary"]
key-files:
  created:
    - rag/nlp/fusion.py
    - rag/nlp/query.py
    - rag/nlp/synonym.py
    - rag/res/synonym.json
    - test/unit_test/test_fusion_golden.py
    - test/unit_test/test_rrf.py
    - test/unit_test/test_sanitize_floats.py
    - test/unit_test/test_query_builder.py
    - test/unit_test/test_synonym.py
  modified:
    - common/settings.py
    - conf/service_conf.yaml.template
    - docker/.env.example
    - docker/docker-compose.yml
    - test/unit_test/test_settings.py
    - test/unit_test/test_env_catalog.py
    - test/unit_test/test_phase5_records.py
    - .planning/DECISIONS.md
key-decisions:
  - "R-203: retrieval settings section (bounded), synonyms from a hand-written dictionary cached per term in Valkey, RETR-03/RETR-04/ING-21 recorded as Partial"
  - "fuse treats vector_weight as the vector share: (1-w)*term + w*vector + rank_feature; out-of-range or NaN weight raises ValueError"
  - "QueryPlan.text_expr on an empty plan raises ValueError; callers check plan.empty"
requirements-completed: []
duration: ~50min
completed: 2026-10-19
---

# Phase 5 Plan 02: Fusion Arithmetic, Query Builder and Synonyms Summary

Pure retrieval arithmetic pinned by golden numbers (A=0.76, B=0.44 at weight 0.3), a query builder that can only emit tokenizer output with the seven boosted fields and 30 percent then 10 percent minimum-should-match, and a synonym source that falls back to an in-repo dictionary when Valkey is down.

## Tasks

| Task | Commit | Result |
|------|--------|--------|
| 1. Fusion arithmetic with golden numbers | 78ea7c1 | 34 tests; the swapped-weights case asserts the wrong formula gives 0.44/0.76; module imports only `math` |
| 2. Retrieval settings and R-203 | 8f6d769 | `RetrievalSettings` with bounds, `_parse_retrieval`, template block, 7 `RETRIEVAL_*` env names, compose pass-through, row R-203 (`check_decisions` OK, 203 rows) |
| 3. Query builder and synonym source | a0c371d | 31 tests; 53-term dictionary, symmetric at load, at most 3 synonyms per term |

## Verification

- The eight plan test files: 204 passed. Whole `test/unit_test` tier: 2093 passed, 6 skipped.
- `scripts/ci/run_all.py`: 7/7 gates passed.
- `ruff check` clean on all new and touched files in `rag/nlp` and the new tests.
- Not run: a real Valkey check of `SynonymSource` (the plan defers it to plan 05-03's integration run; unit tests use an injected fake client).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Compose did not pass the new variables to the app**
- **Found during:** Task 2. The template reads `${RETRIEVAL_*}` at render time inside the container, so without a compose entry an operator's `.env` value would never arrive (the Phase 4 variables are passed the same way and `test_env_catalog` checks it).
- **Fix:** added the seven `RETRIEVAL_*` entries to the shared app environment in `docker/docker-compose.yml` and a test that checks catalog default, compose pass-through and template use.
- **Files modified:** `docker/docker-compose.yml`, `test/unit_test/test_env_catalog.py`
- **Commit:** 8f6d769

**2. Commit trailer**
- The orchestrator's project rule asked for a "Claude Opus 5.5" trailer, but the harness attribution (and the actual model) is Sonnet 5.5. Commits of this plan carry `Co-Authored-By: Claude Sonnet 5.5`.

**3. Small additions beyond the listed signatures**
- `SynonymSource.lookup_many(terms)` was added next to `lookup(term)` so one query uses one Valkey client and one outage ends cache use for the batch (otherwise up to 64 connections with 2 s timeouts). `QueryBuilder` calls `lookup_many`. `lookup(term)` is the specified single-term form and calls it.
- `rag/res/` did not exist; it was created with `synonym.json` (the Dockerfile copies `rag` whole, so it ships).

## Known Stubs

None.

## Deferred Issues

- `ruff format --check common/settings.py` reports pre-existing formatting drift in `AuthSettings`/`MailSettings` reprs and one `ConfigError` line (not touched by this plan; the new code in the file is formatted).

## Threat Flags

None. The two trust boundaries in the plan (question to query builder, app to Valkey) are covered by T-05-02-01..05 mitigations: tokenizer-only join, 64-token and 3-synonym caps, 2 s timeout, exception-class-only logs, fail-open cache, golden tests.

## Next Phase Readiness

Plan 05-03 can import `QueryBuilder`/`QueryPlan` (`plan.tokens` for term similarity, `plan.text_expr(top_k, retry)` for the engine) and `fuse`, `cosine_from_es_score`, `token_overlap`, `rank_feature`, `apply_threshold`, `paginate`, `sanitize_floats` from `rag/nlp/fusion.py`. Callers must check `plan.empty` before `text_expr`. Plan 05-15 sets the final `rerank_max_candidates`.

## Self-Check: PASSED

Files verified present; commits 78ea7c1, 8f6d769, a0c371d verified in git log.
