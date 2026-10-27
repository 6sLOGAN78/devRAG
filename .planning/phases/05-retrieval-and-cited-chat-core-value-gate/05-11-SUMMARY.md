---
phase: 05-retrieval-and-cited-chat-core-value-gate
plan: 11
subsystem: cited-chat-turn
tags: [retrieval, citations, completion, persistence, isolation]
requires:
  - phase: 05-09
    provides: "Private sessions, turn locks and rate guard"
  - phase: 05-10
    provides: "Prompt assembly and citation canonicalisation"
provides:
  - "Shared retrieval path for retrieval-test and chat"
  - "One stored cited turn with empty-response, failure and plain-chat paths"
  - "Non-streaming completion route and security harness coverage"
affects: [05-12, 05-13, 05-16, 05-19, 05-25]
tech-stack:
  added: []
  patterns:
    - "Blocking turn preparation and finalisation use named executors"
    - "Model usage writes run in DB_EXECUTOR outside the event loop"
key-files:
  created:
    - api/db/services/chat_turn_service.py
    - api/db/services/chat_turn_reference.py
    - api/apps/restful_apis/completion_api.py
    - test/integration/test_chat_turn_service.py
    - test/testcases/test_chat_flow.py
  modified:
    - api/db/services/llm_service.py
    - api/db/services/retrieval_service.py
    - conf/routes.yaml
    - test/testcases/_matrix_fixtures.py
    - test/testcases/test_phase3_isolation.py
    - test/testcases/test_response_leaks.py
    - .planning/DECISIONS.md
key-decisions:
  - "R-214 records turn order, empty response, storage and async usage writes"
requirements-completed: []
duration: resumed across sessions
completed: 2026-10-26
---

# Phase 5 Plan 11: Cited Chat Turn

A member can ask an assistant a question through `POST /api/v1/chat/completions` with `stream=false`. The service checks visibility and usable datasets, applies the rate guard and session lock, stores the question, retrieves from the real index, builds the prompt, calls the provider and stores the canonical answer with prompt-indexed references. With no bound datasets it runs plain chat; with zero retrieval hits it returns the configured empty response without a chat-model call. A failed provider turn stores a failed assistant message. The route is registered in the generated policy and OpenAPI artifacts and included in the isolation, matrix and leak harnesses.

## Verification

- Turn service integration: 18 passed.
- Live chat flow: 26 cases passed as part of the 31-case chat and ingress suite, including cited retrieval, empty response, history, persistence and refusals.
- Leak sweep: 6 passed with the completion route exercised.
- Broad isolation and tenant matrix: 257 passed, one matrix fixture failed because its own allowed completion changed the before/after snapshot; after removing that call, the affected matrix case passed in isolation. The allowed completion is covered by the chat flow suite.
- Route generation check, Ruff on changed files, unit tests and decision validation passed.

The streaming branch belongs to plan 05-12 and is being verified separately. Changes remain uncommitted under the plan's `do not commit` instruction. Phase requirements remain unticked pending phase verification.
