---
phase: 04-ingestion-pipeline
plan: 04
subsystem: doc-store
tags: [elasticsearch, doc-store, log-redaction, hardening]
requires: []
provides:
  - "DocStoreConnection.stats and frozen StatsResult(count, total)"
  - "simple_query_string text queries, vector mapping check on insert, html-encoded highlights, validated order_by"
  - "redact_value branches for bytes, exceptions and arbitrary objects"
affects: [04-11, 04-35]
tech-stack:
  added: []
  patterns: ["engine-neutral count/sum on the port", "shared Python/Go redaction vectors"]
key-files:
  created: []
  modified:
    - common/doc_store/doc_store_base.py
    - rag/utils/es_conn.py
    - common/log_utils.py
    - test/helpers/doc_store_contract.py
    - test/unit_test/test_doc_store_port.py
    - test/unit_test/test_log_redaction.py
    - test/fixtures/log_redaction_vectors.json
key-decisions:
  - "position_int nested arrays [[page,x0,top,x1,bottom],...] are accepted by the real index and round-trip unchanged via get; no flat stride-5 fallback is needed for plan 04-11"
requirements-completed: [IDX-07, IDX-14, KB-19, CHUNK-16, CHUNK-18]
duration: 25min
completed: 2026-10-17
---

# Phase 4 Plan 04: Doc-store stats and hardening Summary

Count-and-sum `stats` on the doc-store port plus Elasticsearch query, highlight and vector-mapping hardening and non-primitive log redaction, all verified against the real Elasticsearch.

## Tasks

1. Contract cases, then `stats` and query/highlight hardening: commits 1fba735, 3eabcd3 (lint tidy).
   - `StatsResult` and abstract `stats` on the port; `ESConnection.stats` is AND-ed with `kb_id`, validates keys and sum field, returns zero for a missing index.
   - `_text_query` uses `simple_query_string` with flags `AND|OR|PHRASE|PREFIX`, lenient. Punctuation inputs and `*a*b*c*` no longer raise; a leading wildcard matches nothing.
   - `insert` refuses any `q_{dim}_vec` that is not mapped as `dense_vector`; highlights use the html encoder; `order_by` names are checked with the field regex.
   - Contract grew by 8 test functions (plus parametrised cases); 50 integration tests pass.
2. Log redaction (BE-08): commit 4c606ef. `redact_value` masks bytes, exceptions and any other non-primitive; new shared vector passes in Python and `go test ./internal/common/...`.

## Observed position_int shape

The index accepted `position_int=[[1,10,20,30,40],[2,5,6,7,8]]` (insert returned no failures) and `get` returned the identical nested value. Plan 04-11 can use the nested form. Nothing is needed under "Decisions needing rows" for plan 04-35.

## Deviations from Plan

- [Rule 3 - Blocking] The compose stack's Elasticsearch was not running, so integration tests could not execute. Started the infrastructure with `make infra-up` (existing target, no volumes removed); all services became healthy.
- `redact_value` has the signature `(key, value)` in this codebase, so the plan's single-argument examples were adapted accordingly.
- A follow-up style commit (3eabcd3) fixed a ruff E501 and import order introduced in task 1.

## Known Stubs

None.

## Threat Flags

None.

## Self-Check: PASSED

Commits 1fba735, 3eabcd3, 4c606ef exist; modified files present; integration (50), unit (port, layering, redaction) and Go common tests pass.
