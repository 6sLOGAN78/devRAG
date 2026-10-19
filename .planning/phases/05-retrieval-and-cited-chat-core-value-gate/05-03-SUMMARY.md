---
phase: 05-retrieval-and-cited-chat-core-value-gate
plan: 03
subsystem: retrieval
tags: [retriever, elasticsearch, must-not, hybrid-search, rerank, rrf, tenant-isolation]
requires:
  - phase: 05-01
    provides: "strict-xfail must_not contract case, planted vector rows, decision rows R-192..R-202"
  - phase: 05-02
    provides: "fusion arithmetic, QueryBuilder/QueryPlan, SynonymSource, RetrievalSettings"
provides:
  - "rag/nlp/search.py: Retriever, RetrievalRequest, RetrievalResult, Hit (two-stage search, prune seam, reranker seam, RRF)"
  - "Reserved condition key `must_not` in the Elasticsearch adapter search path (text bool and kNN filter), refused by update and delete"
  - "Golden fusion order proved on the real Elasticsearch; foreign dataset id returns nothing; SynonymSource checked on real Valkey"
  - "Decision row R-204"
affects: [05-04, 05-11, 05-24, 05-25]
tech-stack:
  added: []
  patterns: ["exclusions travel inside `condition` under a reserved key because the port forbids new parameters", "caller-supplied seams (document_exists, reranker) keep the Retriever free of MySQL and web imports"]
key-files:
  created:
    - rag/nlp/search.py
    - test/integration/test_retrieval_es.py
    - test/unit_test/test_retriever_unit.py
  modified:
    - rag/utils/es_conn.py
    - test/helpers/doc_store_contract.py
    - test/integration/test_doc_store_es.py
    - test/unit_test/test_phase5_records.py
    - .planning/DECISIONS.md
key-decisions:
  - "R-204: must_not rides in condition; stage-1 pool of top_k with weights 0.001,1 then a kNN-only stage 2 mapped to cosine; pool limit risk R6 accepted; RETR-09 and RETR-13 Partial"
  - "Retriever accepts either RetrievalSettings or the whole Settings object (getattr 'retrieval')"
  - "A reranked result is ordered by blended similarity; an RRF result without rerank is ordered by RRF score with scored similarities reported"
requirements-completed: []
duration: ~40min
completed: 2026-10-19
---

# Phase 5 Plan 03: Retriever over the Real Elasticsearch Summary

A Retriever that builds a `top_k` pool with one text + kNN + weighted-sum search, re-scores it with a kNN-only pass mapped back to cosine, prunes deleted documents, optionally blends a reranker, and passes the golden K/S fusion order on the real engine.

## Tasks

| Task | Commit | Result |
|------|--------|--------|
| 1. `must_not` in the search path | ce7cdf3 | Contract case green (xfail removed, 0 left); update and delete refuse the key; search validates it and never mutates the caller's dict; port file untouched |
| 2. The Retriever | ef82ae1 | 13 unit call-shape tests, 18 integration tests on the real engine and Valkey |
| 3. Row R-204 and the records title | b335d0b | `check_decisions` OK (204 rows) |

## Verification

- `test_doc_store_es.py`: 53 passed (51 before plus 2 new `must_not` tests). `test_retrieval_es.py`: 18 passed. `test_retriever_unit.py`: 13 passed.
- Whole `test/unit_test` tier: 2106 passed, 6 skipped. `scripts/ci/run_all.py`: 7/7 gates passed.
- Acceptance greps: no `xfail` in the contract file; `git diff` of `common/doc_store/doc_store_base.py` empty; `"0.001,1"` present in `search.py`; the cosine mapping is called through `cosine_from_es_score`; no `.update(` in `search.py`.
- Integration tests include `golden_order_at_weight_zero_and_one`, `foreign_dataset_id_returns_nothing`, `deleted_document_is_pruned`, `removed_kwd_rows_are_excluded`. The Phase 5 plan 05-02 hand-off (real Valkey check of `SynonymSource`) is covered by `test_synonym_source_answers_from_the_real_valkey_and_caches`.

## Deviations from Plan

### Auto-fixed Issues

None needed beyond the plan. Small choices the plan left open:

- `Retriever(doc_store, settings, ...)` takes either the `RetrievalSettings` section or the whole `Settings` (it reads `.retrieval` when present), so plan 05-04 can pass whichever it holds.
- `doc_ids=[]` (an empty list, not `None`) returns an empty result without calling the engine; `None` means no document filter.
- A reranker that returns the wrong number of scores or a non-finite score raises `ValueError` (the service maps provider errors; a contract breach is a bug). Scores are clamped to [0, 1].
- In `rrf` mode the text-only search also gets the 10 percent retry when it returns nothing.
- The unit test for an empty plan uses `"?! ..."`: a question made only of stop words falls back to its raw tokens (plan 05-02 behaviour), so it is not empty.
- Commit trailer is `Co-Authored-By: Claude Sonnet 5.5` per the harness attribution.

## Known Stubs

None.

## Deferred Issues

None. Reminder for plan 05-04: check the returned `document_exists` seam is a MySQL read of live document ids; the Retriever never touches MySQL.

## Threat Flags

None. Mitigations T-05-03-01..05 are in place: per-tenant index plus mandatory `kb_id` terms filter (foreign dataset id returns zero hits), `available_int`/`doc_enabled_int`/`removed_kwd` filters and the prune seam (tested), `must_not` refused by update and delete (tested), tokenizer-only query text, and `top_k` and `rerank_cap` bounded in `RetrievalRequest`.

## Next Phase Readiness

Plan 05-04 builds the retrieval service and route over `Retriever.retrieve(request, document_exists=..., reranker=...)`; it must check the returned `RetrievalResult.total`, map `DocStoreError` to the index-unavailable reason and a reranker exception to 502, and turn `Hit` into the reference-chunk JSON shape (positions from `position_int`, `page_dims_flt` to `page_sizes`).

## Self-Check: PASSED

Files verified present; commits ce7cdf3, ef82ae1, b335d0b verified in git log.
