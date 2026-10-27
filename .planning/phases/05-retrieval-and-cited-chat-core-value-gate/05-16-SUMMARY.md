---
phase: 05-retrieval-and-cited-chat-core-value-gate
plan: 16
subsystem: web-chat-services
tags: [sse, fetch, reducer, mappers]
provides:
  - Authenticated bounded POST streaming and canonical turn reducer
  - Typed assistant, session, reference and retrieval services
key-files:
  created: [web/src/services/sse.ts, web/src/services/chat-turn.ts, web/src/services/chat-service.ts, web/src/services/retrieval-service.ts]
  modified: [web/src/constants/api-paths.ts, web/src/constants/app-paths.ts, web/src/services/model-service.ts, web/src/services/chunk-service.ts]
requirements-completed: []
completed: 2026-10-26
---

# Phase 5 Plan 16: SPA Services and SSE Client

Implemented same-origin authenticated POST fetch streaming with the approved parser, a 60 s idle watchdog, bounded incomplete events, typed HTTP/transport errors, current-token 401 purge and cancellation. The reducer appends deltas and replaces them with the canonical final answer, preserving partial text on stop/failure. Explicit mappers retain sparse reference indices and unavailable sources and discard malformed positions/non-finite scores. Registry-derived paths, page-aware document links and rerank model filtering complete the services. R-220 records the contract.

## Verification

Tests were written before the missing modules. All 205 service/constants tests across 16 files passed with maxWorkers=4, plus type checking, production build, records, decision and no-sleep gates. The initial unrestricted worker run timed out starting workers while TEI occupied over 5 GiB; the capped run passed after the test reranker was stopped. The shared existing toPosition helper was exported for reuse. No dependency change occurred beyond plan 05-14's approved additions.

Plan 05-15 remains blocked by B-37 (the approved BGE model's measured latency); this independent service plan does not claim that gate passed. Changes remain uncommitted under the plan's instruction.

## Self-Check: PASSED
