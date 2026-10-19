---
phase: 05-retrieval-and-cited-chat-core-value-gate
plan: 05
subsystem: llm-rerank
tags: [rerank, tei, openrouter, llm-bundle, retrieval, fail-closed, ssrf]
requires:
  - phase: 05-04
    provides: "retrieval_service.search with the Retriever reranker seam, rerank_applied and timings in the view"
  - phase: 05-03
    provides: "Retriever.retrieve(reranker=...), rerank_cap"
  - phase: 05-01
    provides: "fake provider /rerank (TEI) and /api/v1/rerank (OpenRouter)"
provides:
  - "rag/llm/rerank_model.py: Base, TEIRerank, OpenRouterRerank, build_rerank, normalize_rank, RerankResult"
  - "rerank as a model type (bit 16, rerank_id / tenant_rerank_id slots) and the sixth provider row TEI (keyless, rerank only, default http://tei:80)"
  - "ProviderSpec.model_types gating which types a provider accepts; OpenRouter accepts rerank"
  - "LLMBundle(tenant, model_id, 'rerank') with rerank() and async_rerank()"
  - "rerank_id on POST /api/v1/datasets/search with 502 rerank_unavailable and 409 model_unavailable"
  - "Decision rows R-206 and R-207"
affects: [05-06, 05-14, 05-15, 05-24, 05-25]
tech-stack:
  added: []
  patterns: ["driver reads response bodies with a size cap and raises typed errors outside the except block", "provider registry carries the model types it accepts", "service builds the reranker bundle before embedding so a bad model id costs nothing"]
key-files:
  created:
    - rag/llm/rerank_model.py
    - test/unit_test/test_rerank_model.py
  modified:
    - rag/llm/__init__.py
    - api/db/services/llm_service.py
    - api/db/services/provider_service.py
    - api/db/services/tenant_model_service.py
    - api/db/services/model_defaults_service.py
    - api/db/services/retrieval_service.py
    - api/apps/restful_apis/provider_api.py
    - api/apps/restful_apis/retrieval_api.py
    - api/utils/reasons.py
    - test/helpers/fake_provider.py
    - test/unit_test/test_llm_registry.py
    - test/unit_test/test_provider_policy.py
    - test/unit_test/test_phase5_records.py
    - test/integration/test_tenant_model_service.py
    - test/integration/test_provider_service.py
    - test/integration/test_llm_bundle_flow.py
    - test/integration/test_retrieval_service.py
    - test/testcases/test_provider_flow.py
    - test/testcases/test_retrieval_flow.py
    - web/openapi/openapi.json
    - web/src/interfaces/openapi.d.ts
    - .planning/DECISIONS.md
key-decisions:
  - "R-206: rerank is bit 16 with its own default slot; ProviderSpec.model_types gates saves; TEI row is keyless with the exact default address skipping the SSRF guard; LLM-09 Partial"
  - "R-207: OpenRouter offers rerank (D-02 answered); driver built on the workspace key; no live call made in this plan"
  - "A rerank model id that is unknown, over-long or from another workspace is 409 model_unavailable, raised before the question is embedded"
requirements-completed: []
duration: ~3h (spans a session restart)
completed: 2026-10-20
---

# Phase 5 Plan 05: Rerank Drivers, Model Type and Optional Rerank Stage Summary

TEI and OpenRouter rerank drivers with [0, 1] score normalisation, `rerank` as a first-class model type behind a sixth `TEI` provider row, an `LLMBundle` rerank method, and an optional `rerank_id` on the retrieval route that fails closed.

## Tasks

| Task | Commit | Result |
|------|--------|--------|
| 1. Rerank drivers and normalisation | 392f96b | `rerank_model.py` (TEI batches of 32 with `truncate`, OpenRouter with `top_n`, `normalize_rank`, `build_rerank`); TEI registry row and `model_types`; 54 unit tests incl. batch lengths `[32, 32, 6]`, `follow_redirects=False`, SSRF and key-leak cases; fake provider gained scripted rerank failures by path |
| 2. Model type, TEI row, bundle | 6df869e | bit 16 and default slot, `model_types` gate in provider save and add, rerank save-test branch, `LLMBundle` rerank/async_rerank with usage counting, OpenAPI artefacts regenerated; unit, integration and e2e coverage |
| 3. Rerank stage in the route, R-206, R-207 | 13da60b | `rerank_id` on `POST /api/v1/datasets/search`, 502 `rerank_unavailable`, 409 `model_unavailable`; 9 new integration tests, 4 new e2e tests; DECISIONS rows |

## Verification

- `test/unit_test`: 2182 passed, 6 skipped. `scripts/ci/run_all.py`: 7/7 gates. `check_decisions`: 207 rows; `check_generated` and `export_openapi --check` clean after regeneration.
- Integration (`test_tenant_model_service`, `test_retrieval_service`, `test_provider_service`, `test_llm_bundle_flow`): 151 passed.
- E2E (`test_retrieval_flow`, `test_provider_flow`, `test_models_flow`, `test_openapi`, `test_phase3_isolation`, `test_cross_tenant_matrix`, `test_response_leaks`): 240 passed on the rebuilt stack.
- Behaviours proved: rerank order differs from fusion order (weight 1: vector order `s, k`, reranked `k, s`) with `rerank_applied` true and `rerank_similarity` per hit; without `rerank_id` the order is fusion and no rerank request is made; exactly one `/rerank` request per reranked call with at most the cap of documents (integration with a cap of 8 gives 8 of 12); a failing model gives 502 `data.reason == "rerank_unavailable"` with no chunks; unknown, over-long and other-workspace ids give 409 `model_unavailable` and spend no embedding or rerank request; a keyless TEI instance sends no `Authorization` header; a rerank model on OpenAI or a chat model on TEI is `models_invalid` before any request.

## Deviations from Plan

### Auto-fixed Issues

1. **[Rule 3 - Blocking] Fake provider could not select TEI failures.** The TEI wire has no model field, so the existing model-name switch could not script 401/429/500/redirect for TEI. Added `/scripted/<name>/rerank` and `/scripted/<name>/api/v1/rerank` routes and a `rerank_mode` flag ("fail" answers 500 on both rerank endpoints) to `test/helpers/fake_provider.py`, so an e2e test can save a model and then break it (the save test itself calls the model). The file is not in the plan's `files_modified`.
2. **[Rule 3 - Blocking] OpenAPI artefacts drifted.** Widening the provider body literal changed the schema; `web/openapi/openapi.json` and `web/src/interfaces/openapi.d.ts` were regenerated. The regeneration also added the retrieval `SearchResult` schema from plan 05-04, which the artefact lacked. `tsc --noEmit` is clean.
3. **[Environment] Stack restart.** The host restart stopped the dev stack; it was brought back with the project command and rebuilt before the e2e runs. No source change came from it.

### Choices the plan left open

- **Own HTTP session instead of `chat_model._Session`.** The rerank driver streams the response through its own `httpx.AsyncClient(follow_redirects=False)` so it can cap the body size; nothing in `chat_model.py` was renamed or changed.
- **Error mapping.** 402 maps to `ERROR_QUOTA`, 503 to a retryable `ERROR_SERVER` (the API edge reads status 503 as rate-limited), 408 to a retryable timeout, any other 4xx to invalid request, other 5xx to server.
- **The e2e rerank cases use their own workspace.** The retrieval-test limiter (30 per 60 s per workspace and user) would otherwise be spent by the shared owner fixture. The 502 case breaks the model after saving (`rerank_mode`), and the foreign-model case uses a differently named model in a second workspace.
- **Web type unions are not widened.** `ModelType` in `web/src/services/model-service.ts` and the settings schema still read chat or embedding; the models UI is a later plan (noted in R-206).

## Known Stubs

None. A TEI instance saved without an address uses `http://tei:80`, which does not resolve until plan 05-15 adds the container; until then that save fails as a typed 502 `provider_unreachable` (covered by an e2e test) rather than being stubbed.

## Deferred Issues

None. Pre-existing ruff import-order notes in `test/unit_test/test_llm_registry.py` and `test/integration/test_tenant_model_service.py` are outside this plan.

## Threat Flags

None beyond the plan's register. T-05-05-01..05 are mitigated and tested: `url_guard` on every non-default address (default skip by exact match, near-default refused), scrubbed error text and key-absent checks in exceptions and logs, batches of 32 with a 30 s per-batch timeout and a capped candidate count, fail-closed 502 with `rerank_applied` reported, credentials looked up by workspace so a foreign id is `model_unavailable`.

## Next Phase Readiness

Plan 05-06 (calibration) and the live tier can call `LLMBundle(..., "rerank")` and the route's `rerank_id`. Plan 05-15 adds the TEI container and sets the final `rerank_max_candidates`; the models UI plans widen the SPA model-type unions. No OpenRouter rerank request has been made; the single live smoke call belongs to the live tier.

## Self-Check: PASSED

Files verified present (`rag/llm/rerank_model.py`, `test/unit_test/test_rerank_model.py`); commits 392f96b, 6df869e, 13da60b verified in git log.
