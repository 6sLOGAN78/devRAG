---
phase: 05-retrieval-and-cited-chat-core-value-gate
plan: 04
subsystem: retrieval
tags: [retrieval-test, api-route, tenant-isolation, rate-limit, leak-sweep, quart]
requires:
  - phase: 05-03
    provides: "Retriever.retrieve with the document_exists seam, RetrievalRequest, Hit, RetrievalResult"
  - phase: 05-02
    provides: "RetrievalSettings (top_k, rerank_max_candidates, rate_max, rate_window_seconds), SynonymSource, sanitize_floats"
provides:
  - "api/db/services/retrieval_service.py: search(principal, scope, body, settings, doc_store=None, embedder=None) and retrieval_rate_guard"
  - "POST /api/v1/datasets/search (Python-owned, registry row implemented, matrix row datasets.retrieval_test enforced)"
  - "api/db/services/chunk_view.py: positions_of, page_sizes_of, merge_page_sizes, chunk_view_fields shared by the chunk list and the retrieval view"
  - "Isolation invoker, cross-tenant matrix check and leak-sweep exerciser for the route; decision row R-205"
affects: [05-05, 05-11, 05-24, 05-25]
tech-stack:
  added: []
  patterns: ["service takes doc_store and embedder as optional seams, production passes neither", "rate guard in the provider pool before the service, keyed per workspace and user", "one 404 for the whole request when any dataset id cannot be opened"]
key-files:
  created:
    - api/db/services/chunk_view.py
    - api/db/services/retrieval_service.py
    - api/apps/restful_apis/retrieval_api.py
    - test/unit_test/test_chunk_view.py
    - test/integration/test_retrieval_service.py
    - test/testcases/test_retrieval_flow.py
  modified:
    - api/db/services/chunk_service.py
    - api/utils/reasons.py
    - api/apps/__init__.py
    - api/apps/route_policy_gen.py
    - internal/common/route_policy_gen.go
    - conf/routes.yaml
    - test/testcases/test_phase3_isolation.py
    - test/testcases/_matrix_fixtures.py
    - test/testcases/test_response_leaks.py
    - test/unit_test/test_phase5_records.py
    - .planning/DECISIONS.md
key-decisions:
  - "R-205: body bounds (question 2000, ids 1..10, size 1..100, top_k 16..setting), embedding_mismatch for mixed models, 45 s handler timeout, rate key retrieval:{tenant}:{user}, response keys; RETR-16 Partial"
  - "The rate guard runs before the datasets are opened, so a refused request also spends a ticket"
  - "A malformed dataset id in the body is a 400 fields_invalid (shape check); an absent, foreign or invisible well-formed id is the one 404"
requirements-completed: []
duration: ~1h45m
completed: 2026-10-19
---

# Phase 5 Plan 04: Retrieval-test Route Summary

`POST /api/v1/datasets/search` runs a question through authorisation, one query embedding, the 05-03 Retriever and a MySQL document-existence prune, and answers scored hits with positions and page sizes. Isolation, the cross-tenant matrix and the leak sweep all cover it.

## Tasks

| Task | Commit | Result |
|------|--------|--------|
| 1. Chunk view helper and retrieval service | 70d944e | `chunk_view` moved out of `chunk_service` unchanged (24 chunk-service integration tests still green); `retrieval_service` with 36 integration tests on the real MySQL, Elasticsearch and Valkey |
| 2. Route, registry row, e2e flow | 4c98e73 | `retrieval_api` blueprint, registry row `implemented: true`, generated route policy files, 12 e2e tests on the rebuilt stack |
| 3. Isolation, matrix, leak sweep, R-205 | d5f4797 | invoker, ID row, provider-calling row, matrix `resource_of` branch and `NO_ID_CHECKS` entry, sweep exerciser plus a log scan, R-205 |

## Verification

- `test/unit_test`: 2114 passed, 6 skipped. `scripts/ci/run_all.py`: 7/7 gates. `scripts/gen_routes.py --check`: clean. `check_decisions`: 205 rows.
- `-m integration test_retrieval_service.py test_chunk_service.py`: 60 passed.
- `-m e2e test_retrieval_flow.py`: 12 passed. `-m e2e test_phase3_isolation.py test_cross_tenant_matrix.py test_response_leaks.py`: 203 passed.
- Behaviours proved: weight 0 versus 1 order with planted vectors (service level), `similarity == term_similarity` at weight 0 and `== vector_similarity` at weight 1 (e2e), higher threshold gives fewer hits, `doc_ids` narrows, a disabled chunk is absent, page 2 of size 2 is stable, exactly one embedding request per call, byte-identical 404 bodies for a non-member, a foreign dataset id, a random id and a mixed list, a refused request never reaches the provider, NaN and Infinity never reach the body, a deleted document is pruned, the rate limit answers 429 with Retry-After, and the question text appears in no stack log line.

## Deviations from Plan

### Auto-fixed Issues

None needed. Choices the plan left open or that differ from its wording:

1. **[Plan wording] `NORMAL_IS_REFUSED_ON_A_RESOURCE` is not extended.** The invoker searches A's team dataset, which a normal member may open, so a member succeeds there. The private-dataset refusal for a member, an admin and the owner is its own test, `test_a_retrieval_test_over_a_private_dataset_is_the_one_404_for_everyone_but_its_creator`, plus the matrix check. The row is in `ID_ROWS`, `PROVIDER_CALLING_ROWS` and `INVOKERS`.
2. **Service signature.** `search(principal, scope, body, settings, ...)` takes the `ActingScope` (the artifact line in the plan) instead of a bare tenant id.
3. **`chunk_view` signatures.** `page_sizes_of(row, wanted=None)` works per row and `merge_page_sizes` orders the union, which reproduces the old aggregated behaviour of the chunk list exactly.
4. **Malformed dataset id is 400.** The plan lists both "32-hex ids" and "malformed id" in the leak sweep. A malformed id is a shape error (`fields_invalid`); well-formed ids that cannot be opened are the one 404.
5. **Rate guard order.** It runs before the datasets are opened (the plan's handler order), so a refused request also spends a ticket. Recorded in R-205.
6. **`web/src/constants/api-routes.generated.json` did not change** when `gen_routes.py` ran: Python-owned rows do not alter it. The Go and Python route policy files and nothing in Nginx changed either, because the existing `^~ /api/v1/datasets/` family already covers the path.
7. **Extra coverage.** The leak sweep gained a log scan proving the question text is never logged; the e2e gained a mixed-id 404 case.

## Known Stubs

None. `rerank_similarity` is emitted only when a hit carries one; `rerank_id` and the reranker seam arrive in plan 05-05, and `timings.rerank_ms` is 0 until then.

## Deferred Issues

None. The pre-existing ruff F811 notes in `test/testcases/test_document_detail_flow.py` are outside this plan.

## Threat Flags

None beyond the plan's register. T-05-04-01..06 are mitigated and tested: per-id `load_visible_dataset` with the acting tenant check and one 404 body, `forbid_unless(datasets, retrieval_test)`, rate guard failing closed plus question, size and timeout caps, no question text or key in logs or bodies (log scan, key scan), `sanitize_floats` (injected NaN test), identical 404 for absent, foreign and invisible ids.

## Next Phase Readiness

Plan 05-05 adds `rerank_id` to the body and a reranker to the `retrieve` call in `retrieval_service.search`; the view already carries `rerank_applied`, `rerank_ms` and the optional `rerank_similarity`. Plans 05-08 and later find the `/api/v1/chats` and `/api/v1/chat/` prefixes already in the isolation table.

## Self-Check: PASSED

Files verified present; commits 70d944e, 4c98e73, d5f4797 verified in git log.
