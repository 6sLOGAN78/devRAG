# Phase 5 - Shared Contracts

Planner artifact. Every Phase 5 plan cites this file so names, shapes and ids cannot drift between plans. Sources: `05-CONTEXT.md` (D-01..D-26), `05-RESEARCH.md` (Patterns 1-7), `05-PATTERNS.md`, `05-UI-SPEC.md` (Notes for the planner). Where this file and a plan disagree, the plan's `must_haves` win and the plan must say so.

## 1. Module map (owner = the plan that creates it)

| Path | Plan |
|------|------|
| `rag/nlp/fusion.py`, `rag/nlp/query.py`, `rag/nlp/synonym.py`, `rag/res/synonym.json` | 05-02 |
| `rag/nlp/search.py` (Retriever), `es_conn.py` `must_not` | 05-03 |
| `api/db/services/retrieval_service.py`, `api/apps/restful_apis/retrieval_api.py`, shared positions helper `api/db/services/chunk_view.py` | 05-04 |
| `rag/llm/rerank_model.py`, `TEI` provider row, `rerank` model type | 05-05 |
| `api/db/migrations/0003_chat_assistants.py`, `Dialog.created_by`, `Dialog.permission`, `assistant_visible`, `can_manage_assistant`, `api/db/services/dialog_service.py` | 05-07 |
| `api/apps/restful_apis/chat_api.py` (assistants) | 05-08 |
| `api/db/services/conversation_service.py`, session and feedback routes (in `chat_session_api.py`) | 05-09 |
| `rag/prompts/generator.py`, `rag/prompts/citations.py` | 05-10 |
| `api/db/services/chat_turn_service.py`, `api/apps/restful_apis/completion_api.py` | 05-11 (non-stream), 05-12 (stream) |
| `web/src/services/{sse,chat-service,retrieval-service}.ts`, hooks, routes | 05-16 |
| `web/src/components/markdown-content/*` | 05-17 |
| `web/src/pages/chat/assistant-dialog/*`, `components/ui/range-field.tsx` | 05-18 |
| `web/src/pages/chat/*` | 05-19, 05-20, 05-21 |
| `web/src/pages/dataset/testing/*` | 05-22 |

## 2. Settings keys (`common/settings.py`, template `conf/service_conf.yaml.template`, catalog `docker/.env.example`)

`retrieval` (05-02): `top_k` 1024 (`RETRIEVAL_TOP_K`, 16..10000), `rerank_max_candidates` 64 interim (`RETRIEVAL_RERANK_MAX_CANDIDATES`, 8..1024; final value set by 05-15), `msm_percent` 30, `msm_retry_percent` 10, `synonym_ttl_seconds` 86400, `rate_max` 30 and `rate_window_seconds` 60 (retrieval-test calls per tenant and user).
`chat` (05-09): `stream_deadline_seconds` 300 (`CHAT_STREAM_DEADLINE_SECONDS`, 30..3600), `max_question_chars` 8000, `max_session_messages` 400, `rate_max` 30, `rate_window_seconds` 60, `message_page_size` 50.

## 3. Reasons (`api/utils/reasons.py`, add only the missing names)

`datasets_unavailable`, `turn_in_progress`, `session_full`, `assistant_dataset_not_shared` (data `dataset_ids`), `assistant_has_member_chats` (data `count`), `rerank_unavailable`, `question_invalid`. Existing and reused: `model_unavailable`, `index_unavailable`, `duplicate_name`, `provider_timeout`, `provider_refused`, `provider_rate_limited`, `busy`, `forbidden`.
Rule: a missed id, another workspace's id, a private assistant seen by a non-creator (owner and admin included) and another user's session are all the one NOT_FOUND body. A provider failure is never 401.

## 4. JSON shapes (keys never include `status`, `source`, `dialog_id`, `password`, `secret`, `salt`, `ticket`, `otp`, `access_token`; the leak sweep bans them)

Assistant view: `id, name, icon (detail only), permission ("me"|"team"), created_by, kb_ids (only ids the reader can open), unavailable_datasets (int, per reader), members_with_chats (int, detail only, for callers who can manage: distinct members other than the caller with at least one session), llm_id, rerank_id, similarity_threshold, vector_similarity_weight, top_n, prompt_config {system, prologue, empty_response}, llm_setting, update_time`.
Session view: `id, chat_id, name, create_time, update_time`; detail adds `messages` (chronological, one page ending before the optional `before=<message_id>`; `limit` default 50) and `has_earlier`.
Message: `id, role, content, created_at`; assistant adds `reference {chunks: [...]}, finish ("complete"|"stopped"|"failed"), usage {input, output, total, estimated}, latency_ms, empty (bool), feedback ("up"|"down"|null)`.
Reference chunk: `index` (0-based, equals the `##N$$` marker), `chunk_id, doc_id, doc_name, dataset_id, content, positions [{page,x0,x1,top,bottom}], page_sizes {"<page>": [w,h]}, similarity, term_similarity, vector_similarity, rerank_similarity?`; after read-time redaction `{index, unavailable: true}`.
Retrieval hit: the reference chunk without `index`. Retrieval response: `total, chunks, doc_aggs, rerank_applied, timings {embed_ms, search_ms, rerank_ms}`. Floats pass `sanitize_floats` (NaN, Infinity become null).
Completion request: `chat_id, session_id?, message, stream (default true), tenant_id?`. Frame: `data: {"code":0,"message":"","data":{...}}\n\n`. While `final` is false: `answer` (delta), `reference` null, `session_id`, `message_id`, `final`. Final frame: `answer` (canonical full text), `reference`, `usage`, `latency_ms`, `finish`, `empty?`, `notice {unavailable_datasets}`, `final: true`. Then `data: [DONE]\n\n`. After the first byte a failure is a frame with non-zero `code`, `data.reason`, `final: true`, then `[DONE]`. Before the first byte every failure is a normal HTTP status with the envelope.

## 5. Routes (all owner python, auth api, roles [owner, admin, normal], scope tenant, in `conf/routes.yaml`)

`POST /api/v1/datasets/search` (matrix row `datasets.retrieval_test`, existing `^~ /api/v1/datasets/` family), `GET|POST /api/v1/chats`, `GET|PUT|DELETE /api/v1/chats/{chat_id}`, `GET|POST /api/v1/chats/{chat_id}/sessions`, `GET|DELETE /api/v1/chats/{chat_id}/sessions/{session_id}`, `POST /api/v1/chats/{chat_id}/sessions/{session_id}/messages/{message_id}/feedback`, `POST /api/v1/chat/completions`. New families (body_limit 1m): exact `/api/v1/chats`, prefix `/api/v1/chats/`, exact `/api/v1/chat/completions`. After every registry edit: `uv run python scripts/gen_routes.py` then `--check`.
Per-route definition of done (Phase 4 missed 7 routes): registry row `implemented: true`, invoker in `test_phase3_isolation.py` (`INVOKERS`, `ID_ROWS`, `NORMAL_IS_REFUSED_ON_A_RESOURCE`, `PROVIDER_CALLING_ROWS`, `PHASE3_PREFIXES` including `/api/v1/chats` and `/api/v1/chat/`), `resource_of` branch and a `BUILDERS` or `NO_ID_CHECKS` entry in `_matrix_fixtures.py`, a sweep builder in `test_response_leaks.py`.

## 6. Decision and blocker ids (next free: R-192, B-37). Status text for every row: `accepted (auto, not user-reviewed)`

| Plan | Rows | Topics |
|------|------|--------|
| 05-01 | R-192..R-202 | R-26 closed (SSE framing); R-27 refined (marker numbering); retrieval route and tier; similarity semantics; query building; rerank failure closed; assistant schema; chat permissions; unavailable datasets; stopped-turn usage (amends R-149); live budget and planted facts |
| 05-02 | R-203 | retrieval settings and synonyms |
| 05-03 | R-204 | `must_not` through `condition`, stage-2 kNN |
| 05-04 | R-205 | retrieval route limits and shape |
| 05-05 | R-206, R-207 | TEI provider and rerank type; OpenRouter rerank driver (D-02 answered) |
| 05-06 | R-208 | calibration result |
| 05-07 | R-209, R-210 | assistant rules as built (D-10, D-23..D-26); assistant view keys |
| 05-08 | R-211 | chat routes and Nginx families |
| 05-09 | R-212 | sessions, turn lock, redaction, feedback route |
| 05-10 | R-213 | prompt, context and injection stance |
| 05-11 | R-214 | turn orchestration, BE-07 |
| 05-12 | R-215 | stream deadline and stop persistence as built |
| 05-13 | R-216 | 8B citation adherence and the model choice (D-05) |
| 05-14 | R-217 | Phase 5 packages and image outcome |
| 05-15 | R-218, R-219 | TEI image and volume (R-218); R-52 closed, rerank cap and memory limit (R-219) |
| 05-16 | R-220 | SPA services and SSE client |
| 05-17 | R-221 | answer rendering rules |
| 05-18 | R-222 | assistant dialog rules |
| 05-19 | R-223 | chat page routes, draft chat, deletion placement |
| 05-20 | R-224 | turn UI states |
| 05-21 | R-225 | source drawer and feedback |
| 05-22 | R-226 | retrieval testing page |
| 05-23 | R-227 | live tier results |
| 05-24 | R-228 | criterion-5 journey |
| 05-25 | R-229 | sharing journeys |
| 05-26 | R-230, R-231 | Partial hand-offs; gate result |
A plan that finds it needs fewer rows keeps the number and writes a short row; it never reuses another plan's number. Blockers use B-37 onward, assigned in the order found.

## 7. Partial requirements (hand-off recorded in DECISIONS and in the ROADMAP Phase 5 note by 05-26; executors never tick REQUIREMENTS.md)

RETR-03 (term weighting left to BM25 IDF), RETR-04 (small in-repo dictionary, no WordNet), RETR-09 (chunk-field conditions only; document metadata filter is advanced), RETR-13 (formula and `pagerank_fea` read; no tag or pagerank producer until Phase 6), RETR-16 (several datasets of one workspace; not several tenants in one call), CHAT-05 (system, prologue, empty response stored; prompt variables other than `{knowledge}` advanced), LLM-09 (TEI and OpenRouter drivers; Jina, Cohere, NVIDIA, Voyage, LocalAI, DashScope direct drivers not built), ING-21 (synonym cache delivered; LLM cache and session store have no consumer yet), UI-22 (GFM only; no math, highlighting, image popovers), UI-25 (dataset, model, threshold, weight, top N, rerank; temperature, top-p, penalties, max tokens controls not drawn).

## 8. Live budget (D-06)

At most 15 chat turns reach the model per gate run (planned 9) and about 10 query embeddings; at most 1 OpenRouter rerank smoke call. Probes (calibration about 20 embeddings, adherence 15 chat calls) are one-off and outside the gate budget. The app counts turns from persisted assistant messages with `usage` and not `empty`; the test keeps its own counter; both are asserted.

## 9. Test commands

`uv run python -m pytest ...` (never bare pytest); `(set -o pipefail; ...)` for pipe-to-tail verifies; `uv run python run_tests.py -m unit|integration|e2e|live_model`; `cd web && npx vitest run --project unit`; Go tiers need `SERVICE_CONF`, `E2E_BASE_URL`, `MANUAL_BASE_URL`, `MYSQL_ROOT_PASSWORD` exported and run under bash. No fixed sleeps (`scripts/ci/check_no_sleep.py`): Python uses `test/helpers/wait.py::wait_until`, web uses `waitUntil` from `@/test/wait-until`; "nothing more happens" checks use `await expect(waitUntil(cond, {timeout})).rejects.toThrow(/timed out/)`. Stack rebuild: `docker compose -p devrag-stack --env-file docker/.env -f docker/docker-compose.yml -f docker/docker-compose.dev.yml --profile cpu --profile elasticsearch --profile mail up -d --build` (add `--profile tei-cpu` once 05-15 lands) then `scripts/wait_stack.sh`. Web port 8088.
