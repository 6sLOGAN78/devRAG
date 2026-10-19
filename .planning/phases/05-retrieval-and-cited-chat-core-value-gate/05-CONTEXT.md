# Phase 5: Retrieval and Cited Chat (Core Value Gate) - Context

**Gathered:** 2026-10-19
**Status:** Ready for planning

<domain>
## Phase Boundary

A user can ask a question about an uploaded document and receive an accurate, streamed, cited answer through the real pipeline: hybrid retrieval (keyword + vector), optional real rerank, generation by a real chat model. No stage is mocked.

The phase delivers:
- the retrieval-testing page and API (ranked hits with term, vector and overall similarity; threshold and weight controls);
- chat assistants bound to datasets, with sessions;
- SSE streaming through Nginx, with stop;
- citations whose drawer shows the chunk and the highlighted PDF region;
- the configured empty response;
- cross-tenant isolation of retrieval;
- one automated browser run from registration to a cited streamed answer against the real stack (success criterion 5, the Core Value gate).

Requirements: RETR-01..19, RETR-23, CHAT-01..23, CHAT-31, LLM-09, ING-21, TEN-03, KB-18, UI-05, UI-18, UI-20..25, DEPLOY-18, E2E-07..09, E2E-12. No Phase 6, 7 or 8 work starts until criterion 5 passes (ROADMAP scope note).

</domain>

<decisions>
## Implementation Decisions

### Rerank model source
- **D-01:** A local **TEI (`text-embeddings-inference`) CPU container** running a small reranker (e.g. `BAAI/bge-reranker-base`; research picks the exact model and image tag) is built and is the guaranteed real reranker for success criterion 4. It needs no new key and costs nothing per call. It is a compose service in the docs' deployment set (`Dockerfile_tei`), with a memory cap recorded like the other services.
- **D-02:** Research checks whether **OpenRouter offers a rerank API**. If it does, an OpenRouter rerank driver is also built on the same key (`OPENROUTER_API_KEY`). Either reranker may satisfy criterion 4, and TEI stays the fallback. If OpenRouter has no rerank API, record that as a decision row and use TEI only.
- **D-03:** Rerank is **optional per assistant and per retrieval test**, as in the docs. With no rerank model, ranking is the weighted keyword + vector fusion. The gate and the criterion-4 tests turn rerank on.
- **D-04:** The rerank candidate window keeps the documented default of **1024**, with a configurable cap on the rerank call. Phase 5 times the CPU reranker and records the dev value in a decision row (resolves R-52).

### Answer model and cost
- **D-05:** Answers in the gate, the live tests and the demo use **`meta-llama/llama-3.1-8b-instruct` through OpenRouter** (the existing `LIVE_CHAT_MODEL`) with `baai/bge-m3` embeddings (Phase 3 D-25). If the 8B model cannot reliably follow the `##N$$` citation format (R-27), the plan switches to a stronger OpenRouter model (e.g. `openai/gpt-4o-mini`) and records the evidence and the choice as a decision row. No new provider or key.
- **D-06:** The live budget is **small: about 10–15 real chat calls per gate run**. For example: a few questions, one streamed and stopped answer, one empty-result case, and the browser journey. Live tests assert the count against the cap, in the same way Phase 4 capped embeddings (Phase 4 D-16).
- **D-07:** Accuracy is checked with **planted facts**. Each test question has a known answer placed in exactly one chunk of a test document. The test asserts that the answer cites that chunk (via `##N$$`, resolved to the chunk id) and that the answer text contains the fact's key words. There is **no LLM judge**.

### Assistants: ownership, sharing, data access
- **D-08:** **Any workspace member** can create a chat assistant. This matches datasets.
- **D-09:** An assistant is **private to its creator by default** (`me`) and can be **shared with the team** (`team`), mirroring dataset permission (Phase 3 D-08). The Phase 3 D-27 rule carries over: a private assistant is invisible to everyone else, including owners and admins.
- **D-10:** Dataset binding rule:
  - **A shared (`team`) assistant may only use `team` datasets.**
  - **A private assistant may use any dataset its creator can open.**
  - Sharing an assistant that uses a private dataset is refused with a clear reason.
  - If a bound dataset later becomes private or is deleted, the assistant stops retrieving from it. The plan picks the exact behaviour: excluded silently with a notice, or a refusal.
  - A teammate must never see a private dataset's chunk text through retrieval or citations.
  - Retrieval always filters by tenant and by dataset ids the caller may open (criterion 4).
- **D-11:** **Chat sessions are private to the user who created them**, even on a shared assistant. Another member using the same shared assistant has their own sessions only.

### Assistants: rulings after the UI check (user, 2026-10-19)
- **D-23:** **Switching a shared assistant back to "Only me" is refused while any other member has sessions with it.** The server answers with a clear reason and the count of members with chats; nothing is deleted. Once no other member has sessions, the switch succeeds. No teammate chat is ever deleted by a visibility change.
- **D-24:** **The creator, and workspace owners and admins, may edit a shared (`team`) assistant**: settings, visibility and datasets. Ordinary members can use it but not edit it. A private assistant stays creator-only (D-09 / Phase 3 D-27). An owner or admin narrowing a `team` assistant to "Only me" is subject to D-23, and the assistant then belongs to its creator only.
- **D-25:** **Saving an assistant never unbinds a dataset the saver cannot see.** The server keeps every bound dataset id the saver cannot open and only applies changes to the ids the saver can see. A bound dataset that is unavailable at answer time is skipped for that reader (D-10), with a notice; the notice is computed per reader. If no usable dataset remains for the reader, the chat answers with a refusal (409), not an empty retrieval.
- **D-26:** **Deleting a shared assistant deletes every member's sessions with it**, after a confirmation that states how many members' chats will be removed. Only the creator, an owner or an admin can delete it. This matches dataset deletion.

### Chat page and citations
- **D-12:** **Core assistant settings only** in this phase: name, avatar, bound datasets, chat model, empty-response text, opening greeting, system prompt, similarity threshold, keyword/vector weight, top N and rerank model. Advanced settings move to later phases. These include prompt variables, keyword extraction, multi-turn question refinement, TTS and similar. Any Phase 5 requirement covering them is marked **Partial** with the hand-off recorded, in the same way as Phase 4 D-27.
- **D-13:** **Clicking a citation opens a side drawer**:
  - It shows the chunk text and, for PDFs, the source page with the cited region highlighted, reusing Phase 4's `PagePreview` and box overlay.
  - Non-PDF sources show the chunk text only.
  - The drawer links to the full document viewer (`documentViewerPath`).
  - No hover popover in this phase.
- **D-14:** **Stop keeps the partial answer.** It is saved in the session, marked as stopped, with whatever citations it has. It survives a refresh, like a complete turn (criterion 2).
- **D-15:** When retrieval finds nothing, the assistant replies with its **empty-response text without calling the chat model** (no cost). A friendly default is set (e.g. "I couldn't find anything about that in the selected datasets."), editable per assistant, in English with draft Chinese.

### Carried forward (already decided, not re-asked)
- **D-16:** All chat and embedding calls use **OpenRouter on the user's key** (Phase 3 D-01, D-25). The key lives in `docker/.env` and is never committed, printed or logged; new routes join the leak sweep (Phase 3 D-23).
- **D-17:** Citation marker **`##N$$`** in stored answers (R-27). The prompt, post-processor, stored message and frontend parser all agree.
- **D-18:** SSE framing follows `docs/12-chat/streaming.md`: enveloped frames, reference on the final frame, `data: [DONE]` terminator. Research resolves delta-vs-cumulative and closes **R-26** before planning.
- **D-19:** Tenant isolation: another tenant's assistant, session or dataset id answers like not-found (404, same body); a member lacking the role gets 403 (Phase 3 D-20). Every new route gets a cross-tenant invoker in `test/testcases/test_phase3_isolation.py`, an entry in the cross-tenant matrix and the leak sweep (lesson from Phase 4).
- **D-20:** Python owns the chat and retrieval routes (CLAUDE.md dual-stack table): one envelope `{code, message, data}`, every route in `conf/routes.yaml`. Go's search-bot `retrieval_test` stays as the docs assign. The research must state whether Phase 5's retrieval-testing page calls Python or Go.
- **D-21:** Test discipline (Phase 3 D-22, Phase 4 practice):
  - Write tests first.
  - Run live tiers against the real stack, with no mocks of our own services.
  - No fixed sleeps (`no_sleep` gate; use `waitUntil` / deadline polling).
  - Nothing is weakened or skipped.
  - Any new package needs user approval through a blocking human checkpoint.
- **D-22:** `DocStoreConnection.update(...)` returns False on per-document failures; every write must check it and fail closed (lesson from Phase 4, 04-17).

### Claude's Discretion
- The exact TEI image tag and reranker model, within the docs' TEI deployment and a CPU memory budget.
- The default similarity threshold, keyword/vector weight and top N, taken from the docs (`07-retrieval`).
- Session naming (first question vs "New chat"), message paging, and the layout of the assistant list.
- How a bound dataset that became unavailable is reported (D-10, last bullet).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Retrieval
- `docs/07-retrieval/retrieval-overview.md`, `retrieval-flow.md`: the retrieval pipeline end to end
- `docs/07-retrieval/hybrid-retrieval.md`, `similarity.md`: keyword/vector fusion, weights, term/vector/overall similarity (criterion 1 golden fusion tests)
- `docs/07-retrieval/keyword-search.md`, `full-text-search.md`, `vector-search.md`, `filters.md`: query building, kNN, tenant/dataset filters
- `docs/07-retrieval/reranking.md`, `docs/11-llm/rerank-models.md`, `docs/05-rag-pipeline/reranking.md`: rerank flow and drivers (D-01..D-04)

### Chat
- `docs/12-chat/complete-chat-flow.md`, `chat-architecture.md`: the full chat flow
- `docs/12-chat/streaming.md`: SSE framing (D-18, R-26)
- `docs/12-chat/messages.md`, `conversation.md`, `context.md`, `memory.md`: message and session model, context assembly
- `docs/11-llm/prompt-management.md`, `llm-request-flow.md`, `llm-architecture.md`: prompts, citation instructions, request flow

### End-to-end flows
- `docs/21-end-to-end-flows/ask-question.md`, `rag-answer.md`, `chat-streaming.md`, `ragflow-one-request.md`: the question-to-answer path (criterion 5)

### Deployment
- `docs/18-deployment/` (TEI / `Dockerfile_tei`, compose profiles, Nginx SSE buffering): the reranker container and streaming through Nginx (DEPLOY-18)

### Frontend
- `docs/02-frontend/` (chat pages, components, api-client SSE via fetch + eventsource-parser per CLAUDE.md)

### Project records
- `.planning/DECISIONS.md`: R-26 (SSE framing, open), R-27 (citation marker), R-52 (rerank cap, open)
- `.planning/phases/03-models-knowledge-bases-and-upload/03-CONTEXT.md`: provider, key, permission and isolation decisions carried forward
- `.planning/phases/04-ingestion-pipeline/04-CONTEXT.md`, `04-VERIFICATION.md`: chunk shape, positions, `PagePreview`, deferred items
- `docs/apikey llm.md`: token formats, `used_tokens` tracking (R-49)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `api/db/models/chat.py`: `Dialog` and `Conversation` Peewee models already exist (Phase 3 schema). Research checks whether their fields cover D-09 (permission), D-11 (per-user sessions) and D-14 (stopped flag), or need a migration.
- `api/db/services/llm_service.py` `LLMBundle`: chat/embedding calls through OpenRouter with token accounting; `rag/llm/chat_model.py` and `rag/llm/stream.py` for streaming chat; `rag/llm/embedding_model.py` for query embeddings. There is no rerank driver yet.
- `rag/utils/es_conn.py` `search(...)` with `MatchDenseExpr` kNN (`num_candidates = 2k`, same as the reference) and keyword expressions. Hybrid fusion and the term/vector/overall similarity breakdown are to be built.
- `rag/nlp/tokenizer.py`: the in-repo tokenizer used for `content_ltks` (query keyword side must match it).
- Web:
  - `web/src/pages/chunk/` `PagePreview` and the box overlay (04-30) for the citation drawer (D-13).
  - `documentViewerPath` / `chunkPath` in `app-paths.ts`.
  - `useBlobUrl` (04-32).
  - Polling and mutation hooks (04-25).
  - Per-area locale files (`web/src/locales/areas/{en,zh}/`) and test-server areas (`web/src/test/server-areas/`).

### Established Patterns
- **Routes and checks:** routes are declared in `conf/routes.yaml` with generated policy (`check_generated.py`). Every new route gets a cross-tenant invoker, a matrix `resource_of` entry and leak-sweep builders.
- **Records:** decision rows go in `.planning/DECISIONS.md` (`check_decisions.py`); blockers go in `.planning/BLOCKERS.md`.
- **Live tests** call the real provider and fail without a key (Phase 3 D-04), with a cost cap asserted from counts.
- **Tests:** the stack is rebuilt with the compose `up -d --build` command (`make up` preflight fails on this host; see `04-DEFERRED-CLEAN-ROOM.md`). Tests find containers by compose label, not by name suffix.

### Integration Points
- Retrieval reads the per-tenant index (`index_name(tenant_id)`) built by Phase 4 (`content_ltks`, `q_{dim}_vec`, `available_int`, `doc_enabled_int`, `position_int`, `page_num_int`). Retrieval must respect `available_int` and `doc_enabled_int` (Phase 4 D-26 switch semantics).
- Nginx: SSE locations need `proxy_buffering off` (exists for datasets; extend for chat).
- The task executor and roll-up from Phase 4 are unchanged. ING-21 and KB-18 tie retrieval to ingestion state; research maps them.

</code_context>

<specifics>
## Specific Ideas

- **Gate run:** the browser journey for criterion 5 goes registration → dataset → upload → parse → question → cited streamed answer. It uses the real OpenRouter chat and embedding models and the real reranker, with no fake in any production path.
- **Accuracy:** planted-fact test documents, with one known fact per chunk (D-07).
- **Gate order:** criterion 5 is the gate for all later phases, so the plan should reach a thin end-to-end cited answer early (MVP mode) and widen from there.

</specifics>

<deferred>
## Deferred Ideas

- Advanced assistant settings: prompt variables, keyword extraction, multi-turn refinement, TTS and the rest. These go to a later phase, with the affected requirements marked Partial (D-12).
- Hover preview on citations (D-13).
- A live Ollama or other non-OpenRouter chat provider proof (still Phase 3 D-03 scope).
- From Phase 4, still open: the clean-room exit gate (B-36, `04-DEFERRED-CLEAN-ROOM.md`), the 20,000-page PDF cap review (B-34), coarse PDF chunk boxes (R-190). These affect the citation highlight's precision but not Phase 5's scope.

</deferred>

---

*Phase: 05-retrieval-and-cited-chat-core-value-gate*
*Context gathered: 2026-10-19*
