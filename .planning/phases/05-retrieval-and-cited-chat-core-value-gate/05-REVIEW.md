---
phase: 05-retrieval-and-cited-chat-core-value-gate
reviewed: 2026-10-27
depth: standard
files_reviewed: 55
files_reviewed_list:
  - api/apps/restful_apis/chat_api.py
  - api/apps/restful_apis/chat_session_api.py
  - api/apps/restful_apis/completion_api.py
  - api/apps/restful_apis/retrieval_api.py
  - api/db/services/chat_turn_reference.py
  - api/db/services/chat_turn_service.py
  - api/db/services/conversation_redaction.py
  - api/db/services/conversation_service.py
  - api/db/services/dialog_datasets.py
  - api/db/services/dialog_records.py
  - api/db/services/dialog_rules.py
  - api/db/services/dialog_service.py
  - api/db/services/llm_service.py
  - api/db/services/model_defaults_service.py
  - api/db/services/provider_service.py
  - api/db/services/retrieval_service.py
  - api/db/services/tenant_model_service.py
  - api/db/services/tenant_scope.py
  - rag/llm/rerank_model.py
  - rag/nlp/fusion.py
  - rag/nlp/query.py
  - rag/nlp/search.py
  - rag/nlp/synonym.py
  - rag/prompts/citations.py
  - rag/prompts/generator.py
  - rag/svr/progress.py
  - rag/utils/es_conn.py
  - web/src/hooks/use-chat-request.ts
  - web/src/hooks/use-retrieval-request.ts
  - web/src/services/sse.ts
  - web/src/services/chat-turn.ts
  - web/src/services/retrieval-service.ts
  - web/src/pages/chat/conversation.tsx
  - web/src/pages/chat/index.tsx
  - web/src/pages/chat/delete-dialogs.tsx
  - web/src/pages/chat/message-input.tsx
  - web/src/pages/chat/message-list.tsx
  - web/src/pages/chat/message-item.tsx
  - web/src/pages/chat/use-chat-params.ts
  - web/src/pages/chat/use-stick-to-bottom.ts
  - web/src/components/markdown-content/index.tsx
  - web/src/components/markdown-content/citations.ts
  - web/src/components/source-drawer/index.tsx
  - web/src/components/source-drawer/source-model.ts
  - web/src/pages/chat/assistant-dialog/assistant-form.tsx
  - web/src/pages/chat/assistant-dialog/dataset-checklist.tsx
  - web/src/pages/chat/assistant-dialog/index.tsx
  - web/src/pages/chat/assistant-dialog/schemas.ts
  - web/src/pages/dataset/testing/index.tsx
  - web/src/pages/dataset/testing/retrieval-controls.tsx
  - web/src/pages/dataset/testing/retrieval-results.tsx
  - test/testcases/test_provider_flow.py
  - test/integration/test_completion_stream_app.py
  - test/integration/test_conversation_service.py
  - test/integration/test_rollup.py
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
resolved_findings:
  critical: 3
  warning: 1
status: clean
---

# Phase 5 code review

## Narrative Findings (AI reviewer)

Inline review of the listed runtime paths and their changed-line context, including tenant/session authorization, request validation, retrieval scoring, model error handling, streaming/persistence, citation rendering, source access, workspace fencing and the gate regressions. The phase base is b38c2431878a7cc71477c1f9de8b02fd03addce0; uncommitted/new Phase 5 files and the recovery fixes are included. Generated schemas and dependency locks are checked by the existing generated/package gates. The earlier gate checklist records those checks.

No open BLOCKER or WARNING remains in this review. Three correctness findings and one test-reliability finding were reproduced and fixed as below. Full final tier results belong to 05-GATE-LOG.md; a clean review does not itself claim that the runtime gate or manual UAT passed. No commit was made.

### CR-05-01 — BLOCKER, resolved: turn lease can expire between stages

**Files:** api/db/services/conversation_service.py:148; api/apps/restful_apis/completion_api.py; api/db/services/chat_turn_service.py.

A turn used one fixed lease despite separately bounded preparation, first-token waiting, streaming and finalization. A real Quart/MySQL/Valkey regression shortened the nearly-consumed lease while generation was held and proved that a competing turn acquired the session during finalization.

The owner-checked lease is now renewed after preparation, at streaming start and before finalization. Renewal uses Valkey's token-checked reacquire operation, fails closed for a lost owner and cannot renew a replacement owner's lease. The configured lease duration remains the stream deadline plus 30 seconds at each boundary. Persistence still releases only the original owner's token.

**Regression evidence:** test_slow_finalization_keeps_the_turn_exclusive failed before the fix; owner-renewal and lost-owner checks pass with it. The affected chat/session/stream integration group passes 59 tests in 106.28 s.

### CR-05-02 — BLOCKER, resolved: nonstream finalization can write a late complete answer

**Files:** api/db/services/chat_turn_service.py:247; api/apps/restful_apis/completion_api.py:148.

The synchronous completion worker bounded generation but called finalization directly afterward. The outer request timeout could return while that worker continued and subsequently stored a complete answer.

The API now awaits the asynchronous service entry point. Preparation and finalization use the existing provider executor, persistence/lease work uses the database executor, and each operation has an explicit deadline. A finalizer result arriving after its deadline is discarded; the failed message is persisted by the caller. The synchronous facade drives the same coroutine using its private loop.

**Regression evidence:** the new nonstream finalization test first timed out waiting for the expected response. It now verifies a typed HTTP 504, a failed stored message, and that releasing the delayed finalizer does not replace it with a complete message. Included in the 59 passing affected integration tests.

### CR-05-03 — BLOCKER, resolved: completed ingestion can expose stale document search flags

**File:** rag/svr/progress.py:157.

Ordinary E2E observed 200 completed chunks with mixed doc_enabled_int values after disabling a document during parsing. Roll-up published the finished state before updating chunk flags and replayed the document-enabled snapshot captured before the switch.

The final transition now locks the document, reads its current status, requires a successful document-store flag update and only then publishes the document/log final state. An index refusal leaves the SQL transaction uncommitted and the document running for a later cycle. The unused snapshot field and the unchecked post-completion update were removed.

**Regression evidence:** three new tests failed for stale snapshot use, premature finished-state visibility and ignoring a False update result. All 51 roll-up/document-switch/ingestion-read integration tests pass in 59.22 s.

### WR-05-01 — WARNING, resolved: the default TEI test assumes the service is absent

**File:** test/testcases/test_provider_flow.py:395.

The transitional plan-05-05 assertion required HTTP 502 before plan 05-15 introduced the real service. The final stack correctly returned HTTP 200.

The test now requires successful default-address TEI configuration, the requested rerank model and a persisted provider row. It accepts only success on the final TEI-enabled stack. Focused rerun: one passed, 14 deselected in 3.91 s.

## Remaining verification boundaries

The final full unit/integration/E2E runs, live-model inventory and timing report are tracked in the gate log. Human checks cover word-level highlight alignment, Chinese copy and answer usefulness. Phase 4 B-36 clean-room verification stays deferred and was not run. The recorded paid Phase 5 API/browser result is preserved; deterministic regressions validate the lifecycle fixes without repeating those paid calls.
