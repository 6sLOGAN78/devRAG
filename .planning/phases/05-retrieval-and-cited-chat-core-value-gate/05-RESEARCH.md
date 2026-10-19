# Phase 5: Retrieval and Cited Chat (Core Value Gate) - Research

**Researched:** 2026-10-19
**Domain:** hybrid retrieval over Elasticsearch, cross-encoder rerank (TEI and OpenRouter), RAG prompt and citation handling, SSE chat streaming through Nginx, chat assistant ownership and isolation, React chat and retrieval-test UI
**Confidence:** MEDIUM-HIGH (protocols, store behaviour, repo code and registries verified in this session; CPU timing, citation adherence of the 8B model and MKL behaviour on this CPU are unmeasured and are plan tasks)

## Summary

The pipeline pieces Phase 5 needs mostly exist as ports, not as behaviour. `DocStoreConnection.search` already takes the whole Phase 5 signature and the Elasticsearch adapter already unions a text query with a kNN clause under a mandatory `kb_id` filter. `LLMBundle` already streams chat and embeds queries with usage accounting. `Dialog` and `Conversation` tables exist. What is missing is: the query builder, the fusion and scoring functions, the rerank drivers and a `rerank` model type, the TEI service, the retrieval service and route, assistants, sessions, the completion stream, the prompt and citation post-processor, two small schema columns, and the whole web side (SSE client, chat page, citation drawer, retrieval-test page). No new Python package is needed (numpy is not in `pyproject.toml`; do the arithmetic in pure Python). Frontend needs two to three approved npm packages (`eventsource-parser`, `react-markdown`, `remark-gfm`), each behind a blocking human checkpoint (D-21).

R-26 is closed by this research: **delta frames while streaming, the final frame carries the complete post-processed answer and the `reference`, then `data: [DONE]`.** The three docs disagree on shape (`chat-api.md` and `chat-streaming.md` show deltas, `streaming.md` shows a complete answer on the final frame); that combination satisfies all of them and CHAT-13. Stop is the client aborting the fetch; the server persists the partial answer in a `finally` and marks it stopped. Section "Architecture Patterns, Pattern 1" has the full contract.

Several facts found in this session change the plan and are easy to miss: Quart's `RESPONSE_TIMEOUT` (60 s) silently truncates any stream longer than that unless the response sets `timeout`; the response leak sweep bans the JSON keys `status`, `source` and `dialog_id` outside system rows; `simple_query_string` cannot boost individual query terms (only fields), so the reference's weighted query cannot be reproduced and term weighting must be recorded as Partial; Elasticsearch scores a cosine kNN hit as `(1 + cos) / 2`, which makes the default similarity threshold 0.2 meaningless unless the cosine is mapped back; TEI's `/rerank` rejects more than 32 texts per request by default and its CPU images 1.7.0 to 1.8.1 had broken MKL; and OpenRouter does offer a rerank API (D-02 answered: yes, nine models today).

**Primary recommendation:** Build a thin vertical slice first (assistant record, retrieval without rerank, non-stream then stream completion with `##N$$`, API-level test on the real stack), then add TEI rerank, stop and persistence, the web chat page and drawer, and finish with the live tier and the real-Chrome journey. Keep the fusion arithmetic in pure functions with golden numbers so swapping the weights fails a unit test before any container runs.

## User Constraints (from CONTEXT.md)

<user_constraints>

### Locked Decisions

#### Rerank model source
- **D-01:** A local **TEI (`text-embeddings-inference`) CPU container** running a small reranker (e.g. `BAAI/bge-reranker-base`; research picks the exact model and image tag) is built and is the guaranteed real reranker for success criterion 4. It needs no new key and costs nothing per call. It is a compose service in the docs' deployment set (`Dockerfile_tei`), with a memory cap recorded like the other services.
- **D-02:** Research checks whether **OpenRouter offers a rerank API**. If it does, an OpenRouter rerank driver is also built on the same key (`OPENROUTER_API_KEY`). Either reranker may satisfy criterion 4, and TEI stays the fallback. If OpenRouter has no rerank API, record that as a decision row and use TEI only.
- **D-03:** Rerank is **optional per assistant and per retrieval test**, as in the docs. With no rerank model, ranking is the weighted keyword + vector fusion. The gate and the criterion-4 tests turn rerank on.
- **D-04:** The rerank candidate window keeps the documented default of **1024**, with a configurable cap on the rerank call. Phase 5 times the CPU reranker and records the dev value in a decision row (resolves R-52).

#### Answer model and cost
- **D-05:** Answers in the gate, the live tests and the demo use **`meta-llama/llama-3.1-8b-instruct` through OpenRouter** (the existing `LIVE_CHAT_MODEL`) with `baai/bge-m3` embeddings (Phase 3 D-25). If the 8B model cannot reliably follow the `##N$$` citation format (R-27), the plan switches to a stronger OpenRouter model (e.g. `openai/gpt-4o-mini`) and records the evidence and the choice as a decision row. No new provider or key.
- **D-06:** The live budget is **small: about 10-15 real chat calls per gate run**. For example: a few questions, one streamed and stopped answer, one empty-result case, and the browser journey. Live tests assert the count against the cap, in the same way Phase 4 capped embeddings (Phase 4 D-16).
- **D-07:** Accuracy is checked with **planted facts**. Each test question has a known answer placed in exactly one chunk of a test document. The test asserts that the answer cites that chunk (via `##N$$`, resolved to the chunk id) and that the answer text contains the fact's key words. There is **no LLM judge**.

#### Assistants: ownership, sharing, data access
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

#### Chat page and citations
- **D-12:** **Core assistant settings only** in this phase: name, avatar, bound datasets, chat model, empty-response text, opening greeting, system prompt, similarity threshold, keyword/vector weight, top N and rerank model. Advanced settings move to later phases. These include prompt variables, keyword extraction, multi-turn question refinement, TTS and similar. Any Phase 5 requirement covering them is marked **Partial** with the hand-off recorded, in the same way as Phase 4 D-27.
- **D-13:** **Clicking a citation opens a side drawer**:
  - It shows the chunk text and, for PDFs, the source page with the cited region highlighted, reusing Phase 4's `PagePreview` and box overlay.
  - Non-PDF sources show the chunk text only.
  - The drawer links to the full document viewer (`documentViewerPath`).
  - No hover popover in this phase.
- **D-14:** **Stop keeps the partial answer.** It is saved in the session, marked as stopped, with whatever citations it has. It survives a refresh, like a complete turn (criterion 2).
- **D-15:** When retrieval finds nothing, the assistant replies with its **empty-response text without calling the chat model** (no cost). A friendly default is set (e.g. "I couldn't find anything about that in the selected datasets."), editable per assistant, in English with draft Chinese.

#### Carried forward (already decided, not re-asked)
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

### Deferred Ideas (OUT OF SCOPE)
- Advanced assistant settings: prompt variables, keyword extraction, multi-turn refinement, TTS and the rest. These go to a later phase, with the affected requirements marked Partial (D-12).
- Hover preview on citations (D-13).
- A live Ollama or other non-OpenRouter chat provider proof (still Phase 3 D-03 scope).
- From Phase 4, still open: the clean-room exit gate (B-36, `04-DEFERRED-CLEAN-ROOM.md`), the 20,000-page PDF cap review (B-34), coarse PDF chunk boxes (R-190). These affect the citation highlight's precision but not Phase 5's scope.

</user_constraints>

<phase_requirements>
## Phase Requirements

"Recommended status" is this research's proposal for the planner to confirm; Partial rows need the hand-off recorded in REQUIREMENTS.md and ROADMAP.md as Phase 4 did (D-27).

| ID | Description | Research Support | Recommended status |
|----|-------------|------------------|--------------------|
| RETR-01 | Dense kNN, cosine, `q_{dim}_vec` | Adapter `_knn` exists; Pattern 2 | Full |
| RETR-02 | BM25 over boosted fields | Field list in Pattern 2; boosts go in `fields`, not in the query string | Full |
| RETR-03 | Query normalisation, tokenisation, term weighting, escaping | In-repo tokenizer + stopwords; no per-term weights possible with `simple_query_string` | Partial (term weighting left to BM25 IDF) |
| RETR-04 | Synonym expansion, Redis-cached | Small in-repo dictionary + Valkey `synonym_{term}`; no WordNet (needs `nltk` + corpus) | Partial |
| RETR-05 | Hybrid fusion `FusionExpr("weighted_sum")` in the docstore | Stage 1 of Pattern 2 with the documented `0.001,1` weights | Full |
| RETR-06 | `w_term*S_term + w_vector*S_vector + S_rank_feature` | Pure `fuse()`; golden numbers in Code Examples | Full |
| RETR-07 | RRF `k = 60` option | Two single-signal searches fused client-side; service-level option | Full (not in UI) |
| RETR-08 | Filters `kb_ids`, `doc_ids`, `id`, `available_int`, `removed_kwd`, `must_not` | Adapter lacks `must_not`; extend `_filter_clauses` for `search` only | Full |
| RETR-09 | Metadata conditions to `bool.must` / `must_not` | Chunk-field conditions only; document metadata filter UI is advanced (D-12) | Partial |
| RETR-10 | Prune chunks of deleted documents | One batched `Document.id IN (...)` check on candidate doc ids | Full |
| RETR-11 | Cross-encoder rerank blend | Pattern 3; `tkweight*tksim + vtweight*rerank` | Full |
| RETR-12 | No reranker: KNN + token overlap on ES | Second kNN pass over candidate ids | Full |
| RETR-13 | Rank feature `10*tag + pagerank` | Formula + `pagerank_fea` read; no producer of tags or pagerank exists until Phase 6 | Partial |
| RETR-14 | Threshold default 0.2, stable sort | Pattern 2 step 8; `sorted()` is stable | Full |
| RETR-15 | Pagination over a window of `top` (default 1024) | Pool = `top_k`, rerank cap configurable (D-04) | Full |
| RETR-16 | Several datasets and tenants' indices in one call | Service takes several datasets of one workspace; route pins one acting workspace (R-22, D-26) | Partial |
| RETR-17 | Hit fields incl. term/vector/overall similarity | Response shape in Pattern 2 | Full |
| RETR-18 | Retrieval-test API | New Python route `POST /api/v1/datasets/search` (Q9) | Full |
| RETR-19 | NaN/Infinity to null | `sanitize_floats` at the serialisation edge | Full |
| RETR-23 | Go retrieval driver (Python implementation in v1) | Python implementation is this phase | Full by Python implementation |
| CHAT-01..04 | Assistant create, list, update, delete | `Dialog`; Pattern 5 | Full |
| CHAT-05 | `prompt_config` (system, prologue, empty response, parameters), `prompt_type` | Stored; variables other than `{knowledge}` are advanced | Partial |
| CHAT-06 | LLM settings | `llm_setting` through `sanitize_gen_conf` | Full |
| CHAT-07 | Retrieval settings | `similarity_threshold`, `vector_similarity_weight`, `top_n`, `top_k`, `rerank_id` columns exist | Full |
| CHAT-08..11 | Session create, list, fetch, delete | `Conversation`; per-user (D-11) | Full |
| CHAT-12, CHAT-13 | SSE completion and frame shape | Pattern 1 (R-26 closed) | Full |
| CHAT-14 | `stream=false` | Same service, one envelope | Full |
| CHAT-15 | Retrieve, rerank, context, generate; plain chat with no datasets | Pattern 4 | Full |
| CHAT-16, CHAT-17 | Context dedupe/truncate/label; history truncation | Pattern 4 | Full |
| CHAT-18 | Markers mapped to `reference.chunks` | Pattern 4 | Full |
| CHAT-19 | `insert_citations` fallback | Only when the answer has no valid marker; one embedding call | Full |
| CHAT-20 | Empty response | D-15; no model call | Full |
| CHAT-21 | Persist turn and references | Pattern 5 | Full |
| CHAT-22 | Stop | Client abort + server `finally` | Full |
| CHAT-23 | Thumbs feedback | New route (legacy `/v1/api/conversation/feedback` not served, R-25) | Full |
| CHAT-31 | Latency and token counts per turn | Stored on the message (`usage`, `latency_ms`) | Full |
| LLM-09 | Rerank drivers normalised to [0,1] | `TEI` and OpenRouter drivers + `normalize_rank`; Jina, Cohere, NVIDIA, Voyage, LocalAI and DashScope direct drivers not built (Voyage, Cohere, Qwen, NVIDIA models are reachable through OpenRouter) | Partial |
| ING-21 | Redis as synonym cache, LLM cache, session store | Synonym cache delivered; LLM cache and session store have no consumer yet | Partial |
| TEN-03 | Tenant-scoped docstore queries | Index per tenant + mandatory `kb_id`; new cross-tenant tests | Full |
| KB-18 | Retrieval test with threshold and weight controls | Route + page | Full |
| UI-05 | SSE client | `fetch` + `eventsource-parser` (checkpoint) | Full |
| UI-18 | Retrieval-testing page | `/dataset/testing?id=` | Full |
| UI-20, UI-21 | Chat playground, streaming render with stop | Chat page | Full |
| UI-22 | Markdown: GFM, highlighted code with copy, KaTeX, image popovers | GFM only (react-markdown + remark-gfm); math, highlighter, image popover need more packages | Partial |
| UI-23 | Citation pills, drawer with chunk text and PDF highlight | D-13 | Full |
| UI-24 | Feedback buttons, hit scores | Buttons + scores in the drawer | Full |
| UI-25 | Assistant configuration | D-12 core fields | Full |
| DEPLOY-18 | TEI image | Compose service `tei` (Standard Stack) | Full |
| E2E-07, E2E-08, E2E-09, E2E-12 | Ask, answer, stream, one-request flows against the real stack | Validation Architecture | Full |

</phase_requirements>

## Project Constraints (from CLAUDE.md)

- `docs/` always wins over `spec.md`, existing code, RAGFlow and judgment. A decision not covered by `docs/` is recorded (what, why, how it fits). Smallest reasonable production-quality choice when unspecified.
- Do not add a service, database, queue, framework or abstraction layer without checking it against `docs/`. (TEI is in `docs/18-deployment/docker.md` and `deployment-overview.md`; a sixth provider entry is a registry row, not a new layer, but record it.)
- Stack pins that matter here: Quart (installed 0.23.1, the CLAUDE.md table still says 0.20.0), quart-schema 0.25.0, Peewee, `litellm==1.103.2`, React 18.3.1, TailwindCSS 3.x, shadcn/ui only, Zustand, TanStack Query inside `use-*-request.ts`, Vite, Vitest. Do not use native `EventSource` (no headers, no POST); use `fetch`.
- No critical placeholders, no mocked stages; every feature verified by realistic execution. Each phase ends in a working state with passing tests.
- Backend: typed interfaces, config/env handling, input validation, structured errors and logging, migrations, transactions, async processing, retries, timeouts, idempotency, health checks, no giant files.
- GSD rule: file changes happen inside a GSD workflow. This document is the researcher's assigned output.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Query tokenisation, fusion arithmetic, citation post-processing | API / Backend (Python `rag/`) | none | Pure functions next to the tokenizer used at index time; golden-testable |
| Hybrid candidate search | Database / Storage (Elasticsearch) | API / Backend | The engine does BM25 + kNN union; the backend owns the scope filter and the second kNN pass |
| Cross-encoder rerank | Separate model server (TEI container, or OpenRouter) | API / Backend (driver) | Model inference stays out of the Quart process; the driver only batches and normalises |
| Assistant and session authorisation, isolation | API / Backend (service layer) | Database (MySQL rows) | Object-level rules (`me`/`team`, per-user sessions) cannot live in Nginx or the coarse matrix |
| SSE streaming and stop | API / Backend (Quart) | CDN / Static tier = Nginx (no buffering) | Quart produces frames; Nginx must not buffer or time them out |
| Turn persistence (messages, references, usage) | Database / Storage (MySQL `conversation`) | API / Backend | One JSON message list per session, written under a turn lock |
| SSE parsing, token rendering, citation pills, drawer | Browser / Client | none | Rendering is client work; the server sends canonical `##N$$` text |
| PDF region highlight | Browser / Client (Phase 4 `PagePreview`) | API (page image route) | Boxes are percentages over a server-rendered page image |
| Retrieval-test page | Browser / Client | API / Backend | Calls the Python route; Go search-bot `retrieval_test` is the beta-token Phase 8 surface |
| TEI model cache | Separate container volume | none | `/data` volume; not in MinIO or MySQL |

## Standard Stack

### Core (already in the repo; reuse, do not replace)

| Library | Version (repo) | Purpose | Why standard here |
|---------|----------------|---------|-------------------|
| Quart / Hypercorn | 0.23.1 / 0.18.0 | ASGI app, SSE response | Docs prescribe it; disconnect cancels the handler task [VERIFIED: `.venv/.../quart/asgi.py`] |
| quart-schema + pydantic | 0.25.0 / >=2.13 | Request validation, OpenAPI | Existing route pattern (`parse_api.py`) |
| elasticsearch (py) | >=8.19,<9 (server 8.11.3) | Doc-store adapter | `rag/utils/es_conn.py` exists |
| litellm + openai SDK | 1.103.2 / >=2.20 | Chat and embeddings through `LLMBundle` | Phase 3 R-138 |
| httpx | 0.28.1 | Rerank HTTP calls (TEI, OpenRouter) | Already a dependency; same no-redirect session pattern as `chat_model._Session` |
| valkey (py) | 6.1.1 | Turn lock, synonym cache, rate limits | Already used by `ratelimit.py`, queue |
| xxhash | 4.0.1 | Content-hash dedupe of context chunks (CHAT-16) | Already approved |
| tiktoken (`cl100k_base`) | >=0.12 | Token budget and usage estimates | `rag/nlp/token_count.py` |
| React 18.3.1, react-router 7, TanStack Query 5, Zustand 4, axios, shadcn/Radix, i18next | as in `web/package.json` | Chat and retrieval-test pages | Existing patterns (`use-*-request.ts`, area locale files) |

No `numpy`, `scikit-learn` or `nltk` is installed (`pyproject.toml`). The reference code uses them for cosine and WordNet; do not add them. Pure-Python arithmetic over at most 1024 floats is trivial.

### New infrastructure

| Item | Version | Purpose | Why |
|------|---------|---------|-----|
| TEI CPU image `ghcr.io/huggingface/text-embeddings-inference:cpu-1.9.4` | 1.9.4 (amd64, 239 MB compressed) | Local `/rerank` server | Upstream official image; the tag exists [VERIFIED: ghcr.io registry tag list and manifest, 2026-10-19] |
| Reranker `BAAI/bge-reranker-base` | MIT, 1.11 GB safetensors (+1.11 GB `onnx/model.onnx`) | Cross-encoder | Listed as TEI-supported; has ONNX weights so the ONNX path (not the broken-MKL candle path) is available [VERIFIED: Hugging Face API, TEI README] |

### Supporting (new npm packages, each behind a blocking human checkpoint, D-21)

| Package | Latest | Purpose | When |
|---------|--------|---------|------|
| `eventsource-parser` | 4.1.2 (CLAUDE.md baseline says 1.1.2; the API changed: `createParser({ onEvent })`) | Parse SSE over `fetch` | UI-05. If declined, hand-write a 40-line parser: server frames are single-line JSON and the app controls both ends |
| `react-markdown` | 10.1.0 (peer `react >=18`; CLAUDE.md baseline says 9.1.0) | Safe markdown for answers; raw HTML is escaped by default | UI-22 |
| `remark-gfm` | 4.0.1 | Tables, task lists, strikethrough | UI-22 |

Not recommended now: `remark-math`, `rehype-katex`, `katex`, `rehype-raw`, `dompurify`, `react-syntax-highlighter`, `react-pdf-highlighter`, `@tanstack/react-table`, `react-dropzone` (R-139 stands). Without `rehype-raw` nothing needs sanitising. UI-22 math, highlighting and image popovers become the Partial remainder unless the user approves more packages at the checkpoint.

### Alternatives Considered

| Instead of | Could use | Tradeoff |
|------------|-----------|----------|
| Upstream TEI image | `infiniflow/text-embeddings-inference:cpu-1.8` (CLAUDE.md, ref `.env`) | 3.9 GB because it bakes models in; a frozen 1.8.x snapshot may predate the 1.8.2 MKL fix [CITED: web search result quoting TEI release notes]; upstream is smaller and pinned to a patch release |
| `bge-reranker-base` | `BAAI/bge-reranker-v2-m3` (Apache-2.0, 2.27 GB) | Better quality, about twice the weights and CPU time; upgrade only if planted-fact tests fail on rerank order |
| `simple_query_string` | `query_string` with `^` term boosts (reference) | Boosts possible but BE-06 moved away from it because it throws on user syntax |
| ES-side score for vector similarity | Python cosine from fetched vectors | 4 MB of vectors per query; the second kNN pass keeps vectors in the engine (reference does the same) |
| New `numpy` dependency | Pure Python | Not needed at 1024 floats |

**Installation (web, after the checkpoint approves exact pins):**
```bash
cd web && npm install --save-exact eventsource-parser@4.1.2 react-markdown@10.1.0 remark-gfm@4.0.1
```
No Python package is added. TEI is pulled by compose.

**Version verification (2026-10-19):**
```bash
npm view eventsource-parser version      # 4.1.2, modified 2026-10-12
npm view react-markdown version          # 10.1.0, 2025-03-07
npm view remark-gfm version              # 4.0.1, 2025-02-10
```
TEI 1.9.4 confirmed from the project's published OpenAPI document (`info.version`) and the ghcr tag list (`cpu-1.9`, `cpu-1.9.0` to `cpu-1.9.4`).

## Package Legitimacy Audit

`slopcheck scan` (installed from PyPI; this version has no `--json` and its `install` subcommand installs, so `scan` on a scratch `package.json` was used) returned `3 OK`. Registry facts from `npm view` and the npm downloads API.

| Package | Registry | Age | Downloads (week of 2026-10-10) | Source repo | slopcheck | postinstall | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|-------------|
| eventsource-parser | npm | created 2022-09 | 50.8M | github.com/rexxars/eventsource-parser | [OK] | none (scripts are `build`, `lint`, `test`, `posttest`) | Approved candidate, user checkpoint still required |
| react-markdown | npm | created 2015-05 | 22.7M | github.com/remarkjs/react-markdown | [OK] | none | Approved candidate, checkpoint required |
| remark-gfm | npm | created 2020-10 | 27.6M | github.com/remarkjs/remark-gfm | [OK] | none | Approved candidate, checkpoint required |

**Packages removed due to slopcheck [SLOP]:** none.
**Packages flagged [SUS]:** none.
All three are named in `docs/00-overview/technology-stack.md` through CLAUDE.md, which is the project authority. Pins in CLAUDE.md are older than the registry; the checkpoint must choose the exact versions. No Python package is proposed.

## Architecture Patterns

### System Architecture Diagram

```
Browser (React)
  chat page ── fetch POST /api/v1/chat/completions (Authorization, AbortController) ──┐
  retrieval-test page ── axios POST /api/v1/datasets/search ──────────────────────────┤
                                                                                       ▼
                                   Nginx :8080  (proxy_buffering off, no gzip for SSE, 3600 s read timeout)
                                                                                       ▼
                                   Quart (Python :9380)
        auth gate ─► route (pydantic) ─► service authorisation (assistant visible? session mine? datasets visible?)
                                                                                       │
        ┌──────────────────────────────────────────────────────────────────────────────┘
        ▼
   retrieval service ──► embed question (LLMBundle "embedding" ─► OpenRouter bge-m3)
        │             ──► Stage 1: DocStore.search(text MatchTextExpr + MatchDenseExpr + FusionExpr 0.001,1)
        │                          filter: kb_id IN visible datasets, available_int=1, doc_enabled_int=1 [index ragflow_{tenant}]
        │             ──► prune hits whose document row is gone (MySQL, one query)
        │             ──► Stage 2: kNN-only search over candidate ids ─► clean cosine per chunk
        │             ──► Python: tsim (token overlap), fuse, take top rerank_cap
        │             ──► optional rerank driver ─► TEI :80 /rerank  or  OpenRouter /api/v1/rerank
        │             ──► blend, threshold, stable sort, paginate
        ▼
   hits empty? ──yes──► empty-response text (no model call) ─► persist ─► final frame
        │ no
        ▼
   prompt builder (system + numbered chunk blocks + citation rules; history truncated newest-first)
        ▼
   LLMBundle "chat" async_chat_streamly ─► OpenRouter llama-3.1-8b ──delta──► SSE frame ──► client appends
        ▼ (stream end)                    client abort ─► CancelledError ─► finally: persist partial, finish="stopped"
   post-process: normalise markers, drop invalid indices, fallback insert_citations if none
        ▼
   persist user + assistant message (reference inside the message), usage, latency
        ▼
   final frame {answer (canonical), reference, usage}  ─►  data: [DONE]
```

### Recommended Project Structure

```
rag/nlp/query.py            # QueryBuilder: question -> tokens, stopwords, synonyms, MatchTextExpr (in-repo tokenizer)
rag/nlp/search.py           # Retriever: stages, scoring, rerank hook, pagination (docs path)
rag/nlp/fusion.py           # pure: token_overlap, fuse, rrf, rank_feature, sanitize_floats
rag/nlp/synonym.py          # dictionary + Valkey cache (key synonym_{term})
rag/res/synonym.json        # small curated dictionary written for this project (do not copy the reference file)
rag/llm/rerank_model.py     # Base.similarity, normalize_rank, TEIRerank, OpenRouterRerank (docs path)
rag/prompts/generator.py    # system prompt, chunk block formatter, citation rules (docs path)
rag/prompts/citations.py    # marker regexes, canonicalise, validate, strip for history
api/db/services/retrieval_service.py     # authorisation of dataset ids + Retriever wiring + embedder seam
api/db/services/dialog_service.py        # assistants: CRUD, visibility, dataset binding rules; chat turn orchestration
api/db/services/conversation_service.py  # sessions: per-user, message list, turn lock, partial persistence
api/apps/restful_apis/retrieval_api.py   # POST /api/v1/datasets/search
api/apps/restful_apis/chat_api.py        # chats, sessions, completions (SSE), feedback
api/db/migrations/0003_chat_assistants.py
web/src/services/{chat-service,retrieval-service,sse}.ts
web/src/hooks/use-chat-request.ts, use-retrieval-request.ts
web/src/pages/chat/ (assistant list, settings sheet, session sidebar, message list, input bar, citation drawer)
web/src/pages/dataset/testing/ (retrieval test)
web/src/locales/areas/{en,zh}/chat.json, retrieval.json
docker/docker-compose-base.yml (service tei), docker/docker-compose.dev.yml (mem_limit)
```
File names follow the docs' paths where they exist (`chat_api.py`, `dialog_service.py`, `conversation_service.py`, `rag/nlp/search.py`, `rag/nlp/query.py`, `rag/llm/rerank_model.py`, `rag/prompts/generator.py`). Each stays small; the retrieval pure functions are separate so they can be tested without services.

### Pattern 1: SSE contract (closes R-26)

**What:** Delta frames, a canonical final frame, a terminator, and a stop that needs no extra route.

**Decision text for the register:** Frames are `data: {"code":0,"message":"","data":{...}}\n\n`. While generating, each frame carries `answer` = the new text only (a delta), `reference` = `null`, `session_id`, `message_id`, `final` = `false`. The last content frame has `final` = `true`, `answer` = the complete post-processed answer (markers canonicalised, invalid indices removed), `reference` = the chunk list, plus `usage`, `latency_ms`, `finish`. The stream then ends with `data: [DONE]\n\n`. Clients append deltas while `final` is false and, on the final frame, replace the displayed text with `data.answer`. Reasons: `chat-api.md` and `chat-streaming.md` show deltas, `streaming.md` shows a complete answer plus reference on the last frame, the reference implementation sends deltas and a final frame, CHAT-13 fixes the keys, D-18 puts the reference on the final frame. Replace-on-final self-heals a dropped frame and lets the server canonicalise once.

**Rules:**
- Validate everything that can fail with a normal status (404, 403, 400, 409, 429) before the `Response` is created. Only failures after the first byte use an error frame: `{"code": <non-zero>, "message": "...", "data": {"answer": "", "reference": null, "session_id": ..., "message_id": ..., "final": true, "reason": "<machine reason>"}}` then `[DONE]`.
- Empty retrieval (D-15): one delta frame with the empty-response text, then the final frame with `reference.chunks = []` and `empty: true`; no model call.
- `stream=false` returns one JSON envelope with the final `data` object (CHAT-14).
- Headers: `Content-Type: text/event-stream; charset=utf-8`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`.
- **`response.timeout` must be set.** Quart wraps sending the whole body in `asyncio.wait_for(..., RESPONSE_TIMEOUT)` (60 s) and swallows the `TimeoutError`, so a longer stream is cut with no `[DONE]` [VERIFIED: `quart/asgi.py` lines 109-117, `app.py` default 60]. Set `resp.timeout = settings.chat.stream_deadline_seconds` (proposed 300) on the streaming response.
- Stop: the browser aborts the `fetch`; Nginx closes the upstream; Hypercorn delivers `http.disconnect`; Quart calls `request_task.cancel()` [VERIFIED: `asgi.py` lines 61-71], which raises `CancelledError` at the generator's `await`. The generator's `finally` persists the partial answer. Do the write with `DB_EXECUTOR.submit(...)` (fire and forget, as `page_api._body` does for `pump.close`) so a second cancel cannot skip it. No stop route and no stop frame.
- The message JSON uses the key **`finish`** (`complete` | `stopped` | `failed`), not `status`: the leak sweep bans `status` and `source` outside system rows and also bans `dialog_id` anywhere (`test/testcases/_leak_sweep.py`). Response bodies must say `chat_id`.

### Pattern 2: Retrieval pipeline and scoring

**Inputs:** `question`, visible dataset ids (one acting workspace), `doc_ids?`, `similarity_threshold` (default 0.2), `vector_similarity_weight` (default 0.3), `top_k` (pool, default 1024), `rerank` model (optional), `page` (1), `size`, `fusion` (`weighted_sum` default, `rrf`).

1. **Query.** `tokens = tokenize(question)` from `rag/nlp/tokenizer.py` (the index side uses the same function for `content_ltks`). Drop a small English stopword list; CJK unigrams and bigrams are kept. Synonyms (dictionary, Valkey-cached under `synonym_{term}`) are appended as plain OR tokens. `MatchTextExpr(["title_tks^10","title_sm_tks^5","important_kwd^30","important_tks^20","question_tks^20","content_ltks^2","content_sm_ltks"], " ".join(tokens), top_k, {"minimum_should_match": "30%"})`. Fields not yet written by Phase 4 (`important_*`, `question_tks`) are harmless to query. If the stage-1 search returns nothing, retry once with `10%` (reference behaviour).
2. **Query vector.** `LLMBundle(tenant, dataset.embd_id, "embedding", expected_dimension=dim).encode_queries(question)` in `PROVIDER_EXECUTOR`. R-22: one embedding model per call; mixed `embd_id` is a 400.
3. **Stage 1 (docstore).** `search(select_fields, [], condition, [text, dense, FusionExpr("weighted_sum", top_k, {"weights": "0.001,1"})], None, 0, top_k, [index_name(tenant)], dataset_ids)` with `condition = {"available_int": 1, "doc_enabled_int": 1, "doc_id": doc_ids?}` plus `must_not` when given. The dense clause uses `{"similarity": 0.0}` as a floor, **not** the user threshold (the user threshold applies to the blended score; a high kNN floor would throw away chunks that match by keyword). Weights `0.001,1` are the documented value (`hybrid-retrieval.md`) and only decide pool membership. On a corpus larger than `top_k` chunks, text-only matches sit below all kNN hits; ask for `limit = top_k` and accept (risk R6); the dev and test corpora are far smaller than 1024 chunks.
4. **Safety prune.** One query `Document.id IN (distinct doc_ids)`; drop hits whose document row is gone (RETR-10).
5. **Stage 2 (clean cosine).** A kNN-only search with `condition={"id": candidate_ids}`, `topn=len(ids)`, `{"similarity": 0.0}`, no fusion expression. Elasticsearch scores a cosine hit `(1 + cos) / 2` [CITED: elastic.co dense-vector 8.11], so `vsim = clamp(2*score - 1, 0, 1)`. Using the raw score would compress every unrelated chunk to about 0.65 and the default threshold 0.2 would never reject a vector-only match (0.3 x 0.65 = 0.195 is on the knife edge). This is a deliberate deviation from the reference (it uses the raw score); record it.
6. **Term similarity.** `tsim = |Q ∩ D| / |Q|` with `Q` the de-duplicated query tokens (before synonym expansion) and `D` the chunk's `content_ltks` + `title_tks` tokens (`similarity.md`; uniform weights because there is no term-weight model).
7. **Fuse.** `sim = (1 - w) * tsim + w * vsim + rank_fea`, `w = vector_similarity_weight`. `rank_fea = pagerank_fea` when the field exists, else 0 (tags: Partial). Sort all pool candidates by `sim` (stable).
8. **Rerank (optional).** Take the first `rerank_cap` candidates (config `retrieval.rerank_max_candidates`; value set by the timing task, interim 64 which equals the reference's `_rerank_window`). The driver returns scores in [0,1]; `sim = (1 - w) * tsim + w * rerank + rank_fea`. Candidates beyond the cap are not returned. Fail closed: a rerank failure is a 502 `rerank_unavailable`, not a silent fallback (the gate must prove the stage ran). Report `rerank_applied` in the response.
9. **Threshold, order, page.** Keep `sim >= similarity_threshold`; stable sort descending; `total` = kept count; slice `[(page-1)*size : page*size]`.
10. **Hit shape (RETR-17).** `chunk_id, doc_id, doc_name, dataset_id, content, positions[{page,x0,x1,top,bottom}], page_sizes, similarity, term_similarity, vector_similarity, rerank_similarity?, index`. Top level: `total`, `chunks`, `doc_aggs`, `rerank_applied`, `timings {embed_ms, search_ms, rerank_ms}`. Run all floats through `sanitize_floats` (RETR-19). Reuse `chunk_service._positions` and `_page_sizes` logic (move to a shared helper).

**Adapter changes needed (small, with contract tests):** (a) `_filter_clauses` must accept `must_not` (dict of field to value or list) for `search` only and emit `bool.must_not`; today a dict value raises `InvalidFilter`. (b) `search` must carry `track_total_hits` as it does. (c) Nothing else; `FusionExpr` stays `weighted_sum` only. RRF is done client-side from two single-signal searches (text-only, kNN-only) and is not an adapter feature.

**Golden fusion tests (criterion 1):**
- Unit, no services: `fuse(tsim, vsim, w)` with A=(tsim 1.0, vsim 0.2) and B=(0.2, 1.0). At `w = 0.3`: A = 0.76, B = 0.44, order A,B. If the weights are swapped in code (`w_term = w`), A = 0.44 and B = 0.76 and the assertion on both the numbers and the order fails. Also assert at `w = 0` (A first) and `w = 1` (B first), and that raising the threshold from 0.5 to 0.8 drops B.
- Integration on real Elasticsearch with planted vectors inserted through the port (not the fake provider, whose embeddings do not depend on the text): chunk K (rare keyword, orthogonal vector) and chunk S (no keyword, vector equal to the query vector). `w = 0` ranks K first, `w = 1` ranks S first. The query vector enters through the embedder seam of the retrieval service.
- RRF: ranks (1,2,3) and (3,1,2) with `k = 60` give fixed fractions; assert the numbers.
- `normalize_rank`: pass-through in [0,1]; min-max when out of range; clip when span < 1e-3 (docs `rerank-models.md`).

### Pattern 3: Rerank drivers and the TEI service

- `rag/llm/rerank_model.py`: `class Base` with `async similarity(query, texts) -> RerankResult(scores: list[float], tokens: int, estimated: bool)`; empty query or texts returns zeros; subclasses return raw scores and `Base` applies `normalize_rank`. Reuse `arun_with_retries`, `ModelException` and the `_Session` pattern (no redirects, response hook capturing failed bodies, base URL through `url_guard`).
- `TEIRerank`: `POST {base}/rerank` with `{"query": q, "texts": batch, "raw_scores": false, "truncate": true}`; batches of 32 (TEI's default `--max-client-batch-size` is 32 and a larger request is a 413 [VERIFIED: TEI CLI docs]); the response is an array of `{index, score}` sorted by score, so write `scores[index + offset]`; per-batch timeout 30 s; `raw_scores: false` gives sigmoid probabilities in [0,1] for the BGE classifier head. Token usage is estimated with tiktoken (TEI reports none).
- `OpenRouterRerank`: `POST https://openrouter.ai/api/v1/rerank` with `{"model", "query", "documents": [...], "top_n": len(documents)}`, Bearer key; response `results[{index, relevance_score, document}]`, `usage{search_units,total_tokens,cost}`; no streaming; error codes 400, 401, 402, 403, 413, 429, 502, 503, 524, 529 map like chat errors [CITED: openrouter.ai/docs/api/api-reference/rerank]. Nine rerank models are listed by `GET /api/v1/models?output_modalities=rerank` today (`cohere/rerank-v3.5`, `cohere/rerank-4-fast`, `cohere/rerank-4-pro`, `voyageai/rerank-2.5`, `voyageai/rerank-2.5-lite`, `voyageai/rerank-3`, `voyageai/rerank-3-lite`, `qwen/qwen3-reranker-8b`, `nvidia/llama-nemotron-rerank-vl-1b-v2:free`) [VERIFIED: live API 2026-10-19]. The list price per search is not in that payload (pricing fields read 0); treat it as possibly paid and keep it to one smoke call per gate run.
- Registry (needs a decision row): `TYPE_BITS["rerank"] = 16` (the column comment already reserves bit 16), `_DEFAULT_FIELDS["rerank"] = ("rerank_id", "tenant_rerank_id")` (both columns exist on `tenant` and `dialog`), a provider `TEI` (slug `tei`, keyless, `default_base_url = "http://tei:80"`, rerank only) so the SSRF guard is skipped only for the exact default address (the same rule that skips the guard for the OpenAI and OpenRouter defaults), and `rerank` allowed on OpenRouter. `ProviderSpec` needs a `model_types` field; the save-provider tiny test call needs a rerank branch (query plus two short documents). Without this the guard would reject `http://tei:80` in production, where `allow_private_base_urls` is false.
- Compose service `tei` in `docker/docker-compose-base.yml` (infra file, like Elasticsearch), profile `tei-cpu`, added to `make up`, `infra-up` and `scripts/clean_room.sh` profile lists and to `wait_stack.sh` with its own long deadline:

```yaml
  tei:
    profiles: [tei-cpu]
    image: ${TEI_IMAGE:-ghcr.io/huggingface/text-embeddings-inference:cpu-1.9.4}
    command: ["--model-id", "${TEI_RERANK_MODEL:-BAAI/bge-reranker-base}", "--auto-truncate"]
    environment:
      HF_TOKEN: ${HF_TOKEN:-}          # optional; raises Hugging Face rate limits
    ports:
      - ${BIND_HOST:-127.0.0.1}:${TEI_PORT:-6381}:80   # 6380 is the Redis host port (R-59); not 8080/8088 either
    volumes:
      - tei_data:/data                  # image sets HUGGINGFACE_HUB_CACHE=/data
    networks:
      ragflow:
        aliases: [tei]
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://localhost:80/health"]   # curl is installed in the image Dockerfile
      interval: 15s
      timeout: 5s
      retries: 40
      start_period: 300s                # first start downloads the model
```
  `docker-compose.dev.yml` adds `mem_limit` from the measurement (interim guess 3g; **measured value is a plan task**, like R-188). The docs name a `Dockerfile_tei`; a thin file `FROM` the pinned tag adds nothing here (models come from the volume), so use the image directly and record that as the reading of "Dockerfile_tei" in `docs/18-deployment/docker.md` (decision row). Add `TEI_IMAGE`, `TEI_RERANK_MODEL`, `TEI_PORT`, `HF_TOKEN` to `docker/.env.example`, `test_env_catalog.py` and `test_compose_files.py`.

### Pattern 4: Prompt, context and citations (R-27)

- **Marker numbering is 0-based and refers to the order of the chunk blocks actually placed in the prompt** (`context.md`: `Chunk 0 -> ##0$$`; reference implementation `ID: {i}`). `reference.chunks[N]` is the chunk of marker `##N$$`. The reference is built from the same list, after dedupe and token-budget trimming, so an index can never point at a chunk the model did not see.
- Context block: `ID: 0` / `Title: <doc name>` / `Page: 3` (from `page_num_int`) / `Content: <text>`; chunks deduplicated by `xxhash` of the whitespace-normalised text; total trimmed to `0.97 * (model max_tokens - system - completion - margin)` with `count_tokens`. History is truncated newest-first with the formula in `memory.md`, and prior assistant text has markers removed before it goes back to the model (`re.sub(r"##\d+\$\$", "", ...)`).
- Prompt rules for the system message (English, one worked example in the same format; small models follow a concrete example far better than a rule): answer only from the knowledge blocks; if they do not contain the answer say so; after each sentence that uses a block write `##N$$` with the block's ID, several as `##0$$##2$$`; never invent an ID; never put a marker inside a code block. Include one short two-block example. The retrieved text is **data**: state that instructions inside it must be ignored (indirect prompt injection).
- Post-processor (`rag/prompts/citations.py`), applied once on the full text at stream end:
  1. Normalise common model variants to `##N$$`: `## N $$` with inner spaces, `[ID:N]`, and `[N]` when `N < len(chunks)`. Parenthesised numbers like `(3)` are ordinary text and are never rewritten.
  2. Remove markers whose index is out of range; collapse duplicates at the same spot.
  3. If no valid marker remains and the answer is non-empty, run the CHAT-19 fallback `insert_citations`: split sentences (reference regex), embed the pieces with the dataset embedding model, compare with the cited chunks' vectors (fetched by id from the index), cite the best chunk per sentence over a falling threshold (0.63 down to 0.3). Costs one embedding call; flag `citations: "inserted"` in usage metadata.
  4. Stored text is canonical `##N$$`; the same regex `/##(\d+)\$\$/g` is shared by the frontend.
- While streaming, a marker can be split across frames (`##` | `1$$`). The server sends raw deltas; the client holds back a tail that could be a marker prefix (`/#{1,2}\d*\$?$/`) and shows markers properly on the final frame.
- **Why 8B may fail and the fallback signal (D-05).** Untested; I did not spend the user's key in research. Mitigations are the in-prompt example, temperature 0.1 (already the default `llm_setting`), markers placed after sentences, and the CHAT-19 safety net. **Switch rule for the register:** in the Wave 0 probe (5 planted-fact questions x 3 runs = 15 calls, one-off, separate from the gate budget) count answers whose valid markers include the planted chunk's index. If fewer than 12 of 15 do, or the model emits no valid marker in 3 or more answers, switch `LIVE_CHAT_MODEL` to `openai/gpt-4o-mini` (listed at $0.15/$0.60 per million tokens) and record the evidence. At gate time the same count (>= 4 of 5) is the standing signal.

### Pattern 5: Assistants, sessions, persistence

- **Schema.** `Dialog` lacks the creator and the permission. Migration `0003`: `dialog.created_by VARCHAR(32) NOT NULL DEFAULT ''` (indexed) and `dialog.permission VARCHAR(16) NOT NULL DEFAULT 'me'` (indexed), with `add_column_if_missing`, then `scripts/export_schema.py` and `scripts/gen_go_entities.py` so the Go `--migrate` verification and the schema drift gate stay green. `Conversation` needs nothing: `user_id` (255) already exists (D-11); `dialog.icon` is the avatar; the empty response, greeting and system prompt live in `prompt_config` (`empty_response`, `prologue`, `system`); the stopped marker lives on the message JSON (`finish`), so there is no column for D-14. The `Conversation.reference` column stays `[]`: the reference is stored inside the assistant message as `conversation.md` shows (record this; storing it twice doubles chunk text).
- **Stored message:** `{id, role, content, created_at}`; assistant adds `reference`, `finish`, `usage {input, output, total, estimated}`, `latency_ms`, `empty?`, `feedback?`. Key names avoid the leak-sweep banned list.
- **Visibility.** `tenant_scope.dataset_visible` and `can_manage_dataset` are generic; add thin `assistant_visible` and `can_manage_assistant` wrappers (same logic: a `me` assistant belongs to its creator alone, no owner or admin override; `team` is visible to every active member; manage = creator, owner, admin). Never reuse the dataset name at call sites.
- **Dataset binding (D-10).** Create or update refuses (400/409 with reason `assistant_dataset_not_shared` and the offending ids) when a `team` assistant would bind a dataset that is not `team`; the caller must be able to open every bound dataset (else the one 404). At chat time the retrieval set is `bound ∩ datasets visible to the asking user`, and for a `team` assistant additionally `permission == team`. Excluded datasets are reported in the final frame as `notice: {unavailable_datasets: n}` and on the assistant view; if none remain the turn is a 409 `datasets_unavailable` (not the empty-response text, which would mislead). Deleted datasets are filtered the same way; no cascade on `kb_ids`. Names are unique per workspace (like datasets).
- **Sessions.** `Conversation.user_id = caller`; every read, list, delete, completion filters `dialog_id` and `user_id`. A teammate's session id is the one 404. Deleting an assistant deletes all its sessions (owner/admin/creator).
- **Read-time redaction.** A stored `reference` carries chunk text. When a session is read, check the visibility of each distinct `dataset_id` in it; replace chunks of datasets the reader can no longer open with `{index, unavailable: true}` (keeps the "teammate never sees a private dataset's text" rule after a permission flip).
- **Turn lock and order.** Take a Valkey lock `chat_turn:{session_id}` (`SET NX EX`, TTL = stream deadline) before the first byte; a second concurrent turn is 409 `turn_in_progress`. Persist the user message first (`UPDATE` inside a transaction with the row locked `FOR UPDATE`), so a refresh after a failure still shows the question; append the assistant message at the end or in the `finally`. A stop before the first token stores an assistant message with empty `content` and `finish: "stopped"`; history building skips empty assistant messages.
- **Limits.** Question length cap (proposed 8000 chars), session message cap (proposed 400), completions rate-limited per workspace and user (`common/ratelimit.py`, proposed 30 per 60 s, 429 with `Retry-After`) to bound OpenRouter spend.
- **Usage on stop.** R-149 says an abandoned stream adds no tokens. A stopped answer was still generated and billed by the provider; recommend recording an estimated usage (`estimated: true`) for stops and adding a decision row amending R-149. Without it, the stored `usage` on a stopped turn is the tiktoken estimate and `used_tokens` is not updated.
- **BE-07 (waits for Phase 5).** `async_chat_streamly` and `async_chat` call `_report_usage` (synchronous MySQL `UPDATE`) on the loop, and `LLMBundle.__init__` reads a credential row. Build bundles in `DB_EXECUTOR`, run `_report_usage` through `run_blocking(DB_EXECUTOR, ...)`, and add a unit test that fails when `DB.execute_sql` is entered with a running loop. `_check_target` skips DNS for the documented default hosts (OpenRouter), so it only matters for custom base URLs.

### Pattern 6: Routes (all in `conf/routes.yaml`, owner python)

| Method | Path | Notes |
|--------|------|-------|
| POST | `/api/v1/datasets/search` | Retrieval test (Q9). Body: `dataset_ids[]`, `question`, `doc_ids?`, `similarity_threshold`, `vector_similarity_weight`, `top_k`, `rerank_id?`, `page`, `size`, `tenant_id?`. Matrix row: `datasets.retrieval_test` |
| GET, POST | `/api/v1/chats` | List with `page`, `keywords`; create |
| GET, PUT, DELETE | `/api/v1/chats/{chat_id}` | Read, update (settings, `permission`), delete. Docs list only GET/POST/DELETE; PUT for update follows CHAT-03 |
| GET, POST | `/api/v1/chats/{chat_id}/sessions` | List (mine), create |
| GET, DELETE | `/api/v1/chats/{chat_id}/sessions/{session_id}` | Read with messages (paged), delete |
| POST | `/api/v1/chat/completions` | SSE or JSON; body `chat_id`, `session_id?`, `message`, `stream`; creates the session when absent and returns its id in every frame |
| POST | `/api/v1/chats/{chat_id}/sessions/{session_id}/messages/{message_id}/feedback` | CHAT-23; `thumb: up|down|null`, `comment?` |

New Nginx families are needed because `/api/` falls to the catch-all with a 1024m body limit: `{owner: python, match: exact, path: /api/v1/chats, auth: api, body_limit: 1m}`, a `/api/v1/chats/` prefix and `/api/v1/chat/completions` exact with `streaming: true`; then `uv run python scripts/gen_routes.py` (generates the Nginx config and Vite proxy; `--check` is the drift gate). Chat routes use registry roles `[owner, admin, normal]`, `auth: api`; the docs permission table has no chat row and `test_permissions_table.py` ties `permissions.yaml` to that table, so do not invent a matrix area for chat (record). `proxy_buffering off`, HTTP/1.1, empty `Connection`, `chunked_transfer_encoding on` already come from `docker/nginx/proxy.conf` for every proxied location, and `gzip_types` does not list `text/event-stream`, so DEPLOY-12 already holds; DEPLOY-18 here is the TEI image. Add a streaming assertion to `test_nginx.py`.

### Pattern 7: Frontend

- `web/src/services/sse.ts`: `fetch` POST with `Authorization: Bearer` from `getAuthorization()`, `signal` from an `AbortController` held by the hook, same-origin only, workspace id in the body. `response.ok` and `content-type` are checked before parsing; a 401 on a request that carried the still-current token calls the existing `purgeSession()`; other statuses parse the JSON envelope into `ApiError`. Parse with `createParser({ onEvent })`, ignore comments, treat `[DONE]` as end, cap `maxBufferSize`.
- Answer text is rendered through react-markdown without `rehype-raw`. Pre-process `##N$$` into `[N](#cite-N)` before markdown (a literal `##` would become a heading and `$$` is math syntax if math is ever added); the `a` component renders `#cite-N` links as citation pills and everything else as a normal link with `rel="noopener noreferrer"`. The default `urlTransform` removes `javascript:` URLs.
- Drawer: shadcn `Sheet` (exists). For a PDF source with positions, fetch document detail for the page count and render `PagePreview` with `selection.positions` and `pageSizes` from the stored reference; non-PDF shows text only; a 404 on detail (document deleted or no longer visible) falls back to the stored chunk text; a "Open document" link uses `documentViewerPath`.
- Stop: the Stop button calls `abort()`, then the hook refetches the session so the stored partial (marked stopped) replaces the local one.
- Streaming state in a ref plus `setState` batched per animation frame; lists keyed by message id; `aria-live="polite"` on the answer region; the input stays enabled except while a turn is in flight.
- New areas: `chat`, `retrieval` in `web/src/locales/areas/{en,zh}/`; vitest server areas under `web/src/test/server-areas/`. A `ui_phase` UI-SPEC is a separate artifact and is expected before planning.

### Anti-Patterns to Avoid
- Applying the user's similarity threshold as the kNN floor (drops keyword-only matches; blended score is where the threshold belongs).
- Using the ES `_score` as "vector similarity" without mapping it back to cosine.
- Returning a stream from a generator that can fail validation after headers (authorisation and rate limits first, then `Response`).
- Reading a token from the URL or using native `EventSource`.
- Letting the model's raw text be stored: always store the canonical post-processed text.
- Rebuilding the permission rule per route: use the service helpers so one invoker proves them all.
- Mocking TEI, Elasticsearch or the chat route in the gate. The loopback fake provider is allowed only as the third party's end of the wire (Phase 4 precedent) in deterministic tiers; the live tier and the browser journey use OpenRouter and TEI.

## Don't Hand-Roll

| Problem | Don't build | Use instead | Why |
|---------|-------------|-------------|-----|
| BM25, kNN, union of both | Own scoring engine | The Elasticsearch adapter | Already filters by tenant and dataset |
| Cosine over fetched vectors | Python vector math over 1024 x 1024 floats | Second kNN pass by ids | No vector transport |
| Cross-encoder inference | In-process torch/onnx model | TEI container | `torch` is deliberately absent (R-44) |
| SSE parsing | Regex splitting of chunks | `eventsource-parser` (or a tested minimal parser if declined) | Partial chunks, CRLF, comments |
| Markdown | Custom renderer | react-markdown + remark-gfm | Escapes raw HTML by default |
| Retry/backoff/error mapping for rerank | New loop | `arun_with_retries`, `ModelException` | Same behaviour as chat |
| Rate limiting, turn locks | Ad-hoc dicts | `common/ratelimit.py`, Valkey `SET NX EX` | Multi-process safe |
| Permission rules | Per-route checks | `tenant_scope` helpers + generated policy | Matrix tests cover them |
| Schema change | Raw `ALTER` | Migration runner `add_column_if_missing` + export + Go entity generation | Go `--migrate` verification |
| Wait loops in tests | `sleep` | `test/helpers/wait.py::wait_until`, vitest `waitUntil` | `no_sleep` gate |

**Key insight:** every hard part already has a port or helper; Phase 5 is composition, scoring arithmetic that must be exactly right, and tests that prove each stage ran for real.

## Common Pitfalls

### Pitfall 1: Streams cut at 60 seconds with no error
**What goes wrong:** Answers longer than 60 s end without `final` or `[DONE]`. **Why:** Quart's default `RESPONSE_TIMEOUT` wraps the body send in `wait_for` and ignores the timeout [VERIFIED in source]. **Avoid:** set `response.timeout`; test with a gated slow stream (fake provider holds the stream past 60 s is too slow, so unit-test that the response object carries the configured timeout and integration-test with `RESPONSE_TIMEOUT` lowered in a test app).

### Pitfall 2: Leak sweep rejects the new JSON
**What goes wrong:** `test_response_leaks` fails on keys `status`, `source`, `dialog_id` (and anything matching `password|secret|salt|ticket|otp...`). **Avoid:** `finish` instead of `status`; `chat_id` in every body; extend the sweep builders for every new row (D-19).

### Pitfall 3: Vector similarity that never rejects
**What goes wrong:** Threshold 0.2 passes unrelated chunks; the empty-response path never fires. **Why:** `(1+cos)/2` compression. **Avoid:** map back to cosine (Pattern 2, step 5) and calibrate in Wave 0 with real `bge-m3` vectors (record the relevant and irrelevant `sim` ranges; adjust the default only with evidence).

### Pitfall 4: Weighted query terms silently not applied
**What goes wrong:** Porting the reference's `(term^w)` query. `simple_query_string` supports `^` only in `fields` [CITED: ES 8.11 docs]; in the query string it is not an operator and the character is stripped by the tokenizer anyway. **Avoid:** plain tokens, field boosts only; record RETR-03 Partial.

### Pitfall 5: TEI rejects the batch
**What goes wrong:** `/rerank` with more than 32 texts returns 413; texts over 512 tokens return 413/422 unless truncated; a single request over 2 MB (`--payload-limit`) fails. **Avoid:** batches of 32 and `truncate: true`; do not rely on the server flags; map 413/422/424/429 to typed errors.

### Pitfall 6: TEI CPU image problems
**What goes wrong:** (a) images 1.7.0 to 1.8.1 had broken Intel MKL for models without ONNX weights (fixed in 1.8.2) [CITED: TEI release notes via web search]; the pinned 1.9.4 is past it, and `bge-reranker-base` ships ONNX weights. (b) The image sets `MKL_ENABLE_INSTRUCTIONS=AVX512_E4`; this host's CPU (i5-13500H) reports AVX2, AVX-VNNI and FMA but no AVX-512. Whether MKL treats that as a cap is [ASSUMED]. **Avoid:** the first plan task starts the container and posts one `/rerank`; if it crashes, set `MKL_ENABLE_INSTRUCTIONS=AVX2` and record it. (c) First start downloads up to 2.3 GB (safetensors and ONNX) into the volume; the host has 14 GB free on `/` (93 percent used). (d) A new host port must not collide with Redis 6380.

### Pitfall 7: SSRF guard rejects `http://tei:80`
**What goes wrong:** In production `llm.allow_private_base_urls` is false and the Docker IP is private. **Avoid:** the `TEI` provider spec's `default_base_url` is skipped by exact match only (`_check_target` rule); any other address is still validated.

### Pitfall 8: Stop loses the answer or the usage
**What goes wrong:** The generator is cancelled, nothing is written. **Avoid:** persist in `finally` via `DB_EXECUTOR.submit`; test with a real client that closes the stream after the first frame and asserts `stored.startswith(received_text)` and `finish == "stopped"`.

### Pitfall 9: Two concurrent turns corrupt the message list
**Avoid:** Valkey turn lock plus a `FOR UPDATE` read-modify-write of the JSON list; 409 on contention.

### Pitfall 10: Citation index drift
**What goes wrong:** Marker `##3$$` points at a different chunk than the model saw because of dedupe or trimming after numbering. **Avoid:** number after dedupe and trimming; reference is built from the same list; invalid indices are removed.

### Pitfall 11: Frontend flicker and XSS
**What goes wrong:** Half-typed `##1$` shows as text; `$$` or `##` collides with markdown. **Avoid:** hold back marker-prefix tails; replace markers before markdown; no raw HTML; links `rel="noopener noreferrer"`.

### Pitfall 12: Empty-response test is unstable
**What goes wrong:** An unrelated question still scores above 0.2. **Avoid:** calibrate (Pitfall 3); use a nonsense-token question plus an off-topic question and assert both from stored `sim` values, not from model behaviour.

### Pitfall 13: Valkey eviction
Streams carry no TTL (R-157 set `volatile-lru`); the turn lock and synonym cache must set a TTL (locks) or tolerate eviction (cache).

### Pitfall 14: Dataset rename drift in assistants
A bound dataset can be deleted or made private after binding; always resolve at chat time (Pattern 5), never trust `kb_ids`.

## Code Examples

### Fusion and golden numbers (pure)
```python
# rag/nlp/fusion.py  (no numpy)
def fuse(tsim: float, vsim: float, vector_weight: float, rank_fea: float = 0.0) -> float:
    return (1.0 - vector_weight) * tsim + vector_weight * vsim + rank_fea

def cosine_from_es_score(score: float) -> float:
    return min(1.0, max(0.0, 2.0 * score - 1.0))      # ES scores cosine hits (1 + cos) / 2

# tests: A=(1.0, 0.2), B=(0.2, 1.0)
# w=0.3 -> A 0.76, B 0.44 ; swapped weights -> A 0.44, B 0.76 (order flips, test fails)
def rrf(ranks: list[list[int]], k: int = 60) -> dict[int, float]: ...
```

### SSE frame writer and cancellation-safe persistence (shape)
```python
def frame(data: dict) -> bytes:
    return b"data: " + json.dumps({"code": 0, "message": "", "data": sanitize_floats(data)}, ensure_ascii=False).encode() + b"\n\n"

async def body():
    partial, finished = [], False
    try:
        async for delta in turn.deltas():          # LLMBundle.async_chat_streamly
            partial.append(delta)
            yield frame({"answer": delta, "reference": None, "session_id": sid, "message_id": mid, "final": False})
        final = turn.finalise("".join(partial))     # canonical text, reference, usage
        yield frame({**final, "final": True})
        finished = True
    finally:
        if not finished:                            # CancelledError (client stop) or provider failure
            DB_EXECUTOR.submit(turn.persist_partial, "".join(partial))
        else:
            DB_EXECUTOR.submit(turn.persist_complete, final)
        DB_EXECUTOR.submit(turn.release_lock)
    yield b"data: [DONE]\n\n"                       # skipped on cancel: nobody is listening

resp = Response(body(), mimetype="text/event-stream")
resp.timeout = settings.chat.stream_deadline_seconds    # default 60 s would truncate
resp.headers["X-Accel-Buffering"] = "no"
```
(Persist the complete turn before the final frame in the real code so a crash right after the last frame does not lose it; the sketch shows the cancellation path only.)

### TEI call
```python
async with _Session(timeout) as s:
    r = await s.http.post(f"{base}/rerank", json={"query": q, "texts": batch, "raw_scores": False, "truncate": True})
    for item in r.json():                           # [{"index": 3, "score": 0.97}, ...] sorted by score
        scores[offset + item["index"]] = float(item["score"])
```

### Marker handling
```python
MARKER = re.compile(r"##\s*(\d{1,3})\s*\$\$")        # canonical form after normalisation: ##N$$
VARIANT = re.compile(r"\[(?:ID:\s*)?(\d{1,3})\]")     # [ID:2] and [2] -> ##2$$ when 2 < len(chunks)
# frontend (TypeScript), hold back a possible half marker at the end of the buffer:  /#{1,2}\d*\$?$/
```

### Retrieval filter
```python
condition = {"available_int": 1, "doc_enabled_int": 1}          # D-26 / R-163: both must be 1
condition.update({"doc_id": doc_ids} if doc_ids else {})
```

## State of the Art

| Old approach | Current approach | Impact |
|--------------|------------------|--------|
| Reference stream sent cumulative text (legacy flag still exists) | Delta frames with a final frame | Matches the docs' mixed examples; replace-on-final removes drift |
| Reference cites `[ID:n]` in its current prompt | Project fixes `##N$$` (R-27, docs) | Do not copy the reference prompt text; write ours |
| Reference reranks about 64 candidates per page window | Pool 1024, configurable rerank cap (D-04) | Time it; record the dev value |
| `minio/minio`, Flask etc. | Already settled in Phases 1-4 | Not Phase 5 work |
| TEI baked into `infiniflow/...` images | Upstream image + volume | Smaller, patch-pinned |

**Deprecated/outdated:** CLAUDE.md's `eventsource-parser 1.1.2` and `react-markdown 9.1.0` pins are research baselines, not requirements; Quart 0.20.0 in the same file is 0.23.1 in the repo.

## Assumptions Log

| # | Claim | Section | Risk if wrong |
|---|-------|---------|---------------|
| A1 | TEI treats `MKL_ENABLE_INSTRUCTIONS=AVX512_E4` as a cap and runs on this AVX2-only CPU | Pitfall 6 | Container crashes; first task catches it; fallback `AVX2` |
| A2 | TEI uses the ONNX weights of `bge-reranker-base` on CPU (and downloads both formats) | Pattern 3 | Disk use 1.1 GB instead of 2.3 GB; or MKL candle path (fixed in 1.8.2+) |
| A3 | `bge-reranker-base` fits a 3 GB limit and reranks 64 pairs of 512 tokens within a few seconds on 16 threads | Pattern 3 | Cap value and limit change; both are measured in the first plan wave |
| A4 | `llama-3.1-8b-instruct` follows `##N$$` with an in-prompt example | Pattern 4 | Switch to `gpt-4o-mini` by the stated rule |
| A5 | OpenRouter rerank is priced per search unit and may not be free | Pattern 3 | One smoke call only |
| A6 | `bge-m3` cosine between unrelated English passages is below about 0.45, so default 0.2 on the blended score rejects them | Pitfall 3 | Calibration changes the default threshold |
| A7 | Nginx closes the upstream connection when the client aborts (default `proxy_ignore_client_abort off`) | Pattern 1 | Stop would not cancel the server task; the integration test through the ingress proves it |
| A8 | The TEI runtime image contains `curl` (the main-branch Dockerfile installs it) | Pattern 3 | Use a different healthcheck |
| A9 | Not every OpenRouter rerank model returns scores in [0,1] | Pattern 3 | `normalize_rank` covers it |
| A10 | Dropping a rare-term kNN floor to 0.0 does not hurt recall on corpora under 1024 chunks | Pattern 2 | Large corpora need a two-pass pool |

## Open Questions

1. **Sixth provider `TEI` and `rerank` model type: confirm?**
   - Known: D-01/D-03 need a selectable rerank model; the Phase 3 registry has five providers and chat/embedding only; the SSRF guard blocks `http://tei:80` in production unless it is a spec default.
   - Unclear: whether the user accepts a registry row beyond the docs' five (docs name TEI only as a container; the reference lists "HuggingFace" as a rerank factory).
   - Recommendation: add it (small, recorded). The alternative, a server-config-only reranker with no workspace model row, breaks "rerank model per assistant" and the model selector.
2. **Provider setup inside the browser journey.** Recommend seeding the provider and models by API with the real key (R-147 accepted-exception policy) and driving registration, dataset, upload, parse, assistant and chat through the UI; a UI-typed key puts the secret through CDP calls.
3. **Package pins and scope (checkpoint).** Approve `eventsource-parser@4.1.2` or choose the hand-written parser; approve `react-markdown@10.1.0` + `remark-gfm@4.0.1`; decide whether UI-22 stays Partial (no math, highlighter, image popover).
4. **Stopped-turn usage (amend R-149?).** Recommend recording an estimated usage on stop.
5. **`TEI_PORT` publication.** Needed only for the timing task from the host; recommend loopback publication on 6381, none in production compose.
6. **Do dataset flips (team to me) need a warning when team assistants use the dataset?** Not required by D-10; the notice in the final frame covers users; a dataset-settings warning can be a Partial UI nicety.

## Environment Availability

| Dependency | Required by | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Docker + Compose | stack, TEI | yes | 29.1.3 / v5.0.0 | none |
| Running stack (app, executor, MySQL, Valkey, MinIO, ES, mailpit) | all live tiers | yes (healthy) | ES 8.11.3 | `make up` equivalent compose command (preflight fails on this host, B-36) |
| TEI image and tag | DEPLOY-18 | tag verified on ghcr (not pulled) | cpu-1.9.4, 239 MB compressed | `cpu-1.8.3` |
| Hugging Face reachability | model download in TEI | host reaches `huggingface.co` (HTTP 307) | n/a | pre-seed the `tei_data` volume |
| OpenRouter API key | live tier | present in `docker/.env` (checked by count, never printed) | n/a | none: live tier fails without it (D-04) |
| OpenRouter models | chat, embeddings, rerank | `meta-llama/llama-3.1-8b-instruct` ($0.05/$0.08 per M), `openai/gpt-4o-mini`, `baai/bge-m3` (8194 ctx) listed | n/a | n/a |
| Google Chrome | E2E-12 | yes | 143.0.7499.169 | none |
| Node / uv | web, Python | yes | v22.23.3 / 0.9.18 | none |
| Disk | TEI image + model volume | 14 GB free on `/` (93 percent used) | n/a | clean unused images; preflight threshold |
| RAM | TEI | 15 GiB total, about 7.8 GiB available with the stack up | n/a | smaller reranker or lower limit |
| CPU | TEI | 16 threads, AVX2 + AVX-VNNI, no AVX-512 | n/a | `MKL_ENABLE_INSTRUCTIONS=AVX2` |

**Missing with no fallback:** none. **Missing with fallback:** none outstanding; the TEI image and model are not yet on the host.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 + pytest-asyncio (auto) + pytest-timeout, `filterwarnings=error`; vitest 5.0.3 (`unit` and `live` projects); real headless Chrome over the stdlib DevTools pipe (`test/helpers/chrome_cdp.py`) |
| Config | `pyproject.toml` (markers `unit`, `integration`, `e2e`, `serial`, `smoke`, `live_model`), `run_tests.py`, `web/vitest.config.ts`, `scripts/clean_room.sh` |
| Quick run | `uv run python run_tests.py -m unit` ; `cd web && npx vitest run --project unit` |
| Full suite | `uv run python run_tests.py -m integration` ; `-m e2e` ; `-m "e2e and serial"` ; `-m live_model` ; `cd web && npx vitest run --project live` ; `uv run python scripts/ci/run_all.py` ; phase exit `scripts/clean_room.sh --runs 3` (deferred by the user for Phase 4, B-36) |

### Phase Requirements to Test Map

| Req | Behaviour | Type | Command | Exists |
|-----|-----------|------|---------|--------|
| RETR-06, 14, 15 | golden `fuse`, threshold, pagination; swapped weights fail | unit | `pytest test/unit_test/test_fusion_golden.py -q` | Wave 0 |
| RETR-07 | RRF numbers | unit | `pytest test/unit_test/test_rrf.py -q` | Wave 0 |
| RETR-02, 03, 04 | query builder, stopwords, synonyms, escaping | unit | `pytest test/unit_test/test_query_builder.py -q` | Wave 0 |
| RETR-19 | NaN/Inf to null | unit | `pytest test/unit_test/test_sanitize_floats.py -q` | Wave 0 |
| LLM-09 | `normalize_rank`, driver parsing, batching, error mapping | unit | `pytest test/unit_test/test_rerank_model.py -q` | Wave 0 |
| RETR-01, 05, 08, 10, 12, TEN-03 | planted-vector fusion order, filters (`available_int`, `doc_enabled_int`, `must_not`), pruned deleted docs, foreign dataset id returns nothing | integration (real ES) | `pytest -m integration test/integration/test_retrieval_es.py -q` | Wave 0 |
| DEPLOY-18, LLM-09, RETR-11 | TEI health, `/rerank` order, batch of 32, truncate, reorder vs fusion | integration (real TEI) | `pytest -m integration test/integration/test_rerank_tei.py -q` | Wave 0 |
| CHAT-01..11, D-08..D-11 | assistant CRUD, visibility, binding rules, per-user sessions | integration (real MySQL) | `pytest -m integration test/integration/test_dialog_service.py test/integration/test_conversation_service.py -q` | Wave 0 |
| CHAT-16, 17, 18, 19, R-27 | context builder, trimming, marker normalisation, fallback insertion | unit | `pytest test/unit_test/test_prompt_context.py test/unit_test/test_citations.py -q` | Wave 0 |
| CHAT-12, 13, 21, 22 | frame shape, `[DONE]`, final replace, stop persistence, stream timeout carried | unit + e2e (fake provider stream) | `pytest -m e2e test/testcases/test_chat_flow.py -q` | Wave 0 |
| DEPLOY-18 / Nginx | first frame arrives while the provider is held; last after release | e2e through ingress | `pytest -m e2e test/testcases/test_chat_stream_nginx.py -q` | Wave 0 |
| D-19 isolation | cross-tenant invokers, matrix, leak sweep for every new row | e2e | `pytest -m e2e test/testcases/test_phase3_isolation.py test/testcases/test_cross_tenant_matrix.py test/testcases/test_response_leaks.py -q` (extend; extend `PHASE3_PREFIXES` for `/api/v1/chats`, `/api/v1/chat/`) | extend |
| RETR-18, KB-18, E2E-07 | retrieval-test route on the real stack | e2e | `pytest -m e2e test/testcases/test_retrieval_flow.py -q` | Wave 0 |
| CHAT-20, D-15 | empty response with zero model calls (recorder shows no chat request) | e2e | in `test_chat_flow.py` | Wave 0 |
| D-07, CHAT-18, E2E-08 | planted facts, citation resolves to the planted chunk id, key words present | live_model | `pytest -m live_model test/testcases/test_live_chat.py -q` | Wave 0 |
| RETR-11 criterion 4 | real TEI rerank reorders a crafted case; rerank order equals blended recomputation | live (TEI) + e2e | `test_rerank_tei.py`, `test_live_chat.py` | Wave 0 |
| UI-05 | SSE parser: split chunks, CRLF, comments, `[DONE]`, abort | vitest unit | `cd web && npx vitest run --project unit src/services/sse.test.ts` | Wave 0 |
| UI-18, 20, 21, 22, 23, 24, 25 | components: retrieval test controls, message list, stop, markdown safety, pills, drawer, feedback, settings | vitest unit | `cd web && npx vitest run --project unit` | Wave 0 |
| E2E-09, E2E-12, criterion 5 | register, dataset, upload, parse, assistant, question, streamed cited answer, drawer highlight, refresh keeps turn | real Chrome + live | `pytest -m "e2e and live_model" test/testcases/test_spa_chat_browser.py -q` | Wave 0 |
| UI live | SSE client against the real ingress | vitest live | `cd web && npx vitest run --project live src/pages/chat/chat.live.test.ts` | Wave 0 |

### Sampling Rate
- **Per task commit:** unit tier plus the one integration file touched; vitest for web files touched.
- **Per wave merge:** `-m integration`, `scripts/ci/run_all.py`, `npx vitest run --project unit`.
- **Phase gate:** e2e, serial, live_model, vitest live, real-Chrome journey, all green; `04-VALIDATION.md` precedent for status fields.

### Wave 0 Gaps (before behaviour code)
- [ ] New test files above (write first, D-21).
- [ ] Extend `test/helpers/fake_provider.py` with a gated or delayed chat stream (today `_sse` emits at once) and a record of chat requests, so first-frame-before-last, stop and "no model call on empty" are deterministic without spending tokens.
- [ ] Controlled-vector fixtures through `test/helpers/doc_store_contract.py` for the golden fusion integration test (the fake provider's embeddings do not depend on the text).
- [ ] Planted-fact corpus generator: a TXT of 6 paragraphs, one fact each (unique rare number or name), and a 3-page PDF from `text_pdf` with a different planted fact per page so a cited PDF chunk has boxes.
- [ ] Probe tasks, one-off and not part of the gate budget: (1) TEI smoke on this CPU and timing; (2) calibration of `tsim`, cosine and blended `sim` for relevant and irrelevant queries with real `bge-m3` (embedding calls only, about 20); (3) citation adherence of the 8B model (15 chat calls, rule in Pattern 4).
- [ ] Decision rows R-192 onward (Proposed Decisions below) and B-37 onward for any blocker.

### Rerank timing as a plan task (R-52, D-04)
Start the `tei` service, wait for `/health`, then on the real host: record backend log line, image and volume size, RSS (`docker stats`), cold start time; send `/rerank` with N in {16, 32, 64, 128, 256, 1024} texts at two chunk lengths (about 128 and about 512 tokens, the Phase 4 default `chunk_token_num` is 512), 5 repetitions each, batch 32, record p50 and p95 per N; compute pairs per second. Choose `rerank_max_candidates` as the largest N whose p95 is at most 5 s at 512-token chunks (chat time-to-first-token budget), set `mem_limit` to the measured peak plus 25 percent, and write both in a decision row that resolves R-52. If even N = 16 exceeds the budget, switch to a smaller model or tell the user. No timing number may be written into the plan before this task runs.

### Live budget (D-06) and the gate run
Per gate run, logical chat turns reaching the model, cap 15 (the app counts them from persisted assistant messages with `usage` and not `empty`; the test keeps its own counter and asserts both):

| # | Call | Chat | Embedding (query) |
|---|------|------|--------------------|
| 1 | planted fact in the TXT, rerank on, streamed | 1 | 1 |
| 2 | planted fact in the PDF, rerank on, streamed | 1 | 1 |
| 3 | two more planted facts (one per doc), rerank off, non-stream | 2 | 2 |
| 4 | streamed then stopped | 1 | 1 |
| 5 | off-topic question, empty response | 0 | 1 |
| 6 | citation-adherence sample (3 extra questions) | 3 | 3 |
| 7 | browser journey (one question, one reload) | 1 | 1 |
| 8 | CHAT-19 fallback unit/e2e with the fake provider | 0 | 0 |
| | **Total** | **9** | **10** |
Ingestion embeddings are separate (a few batches for about 30 chunks). The OpenRouter rerank driver gets at most one smoke call per run.

### Criterion-5 browser journey (real Chrome, `ChromeSession`)
Registration form (`/login?mode=register`), land on `/home`; provider and models are seeded by API (Open Question 2); create dataset in the UI; upload the planted PDF through the real file input; Parse; wait until finished; open `/chats`, create an assistant (core fields, rerank model selected, `team` not required); ask the planted question; assert in the DOM, with `wait_for` and no sleeps, that the answer text is observed with at least two different lengths before the done state (streaming), that a citation pill appears, click it, assert the drawer shows the chunk text containing the planted fact and, for the PDF, that a highlight box exists inside the page image (reuse the Phase 4 geometry assertions); reload and assert the same turn and reference are present. First-frame-before-last through Nginx is proven separately and deterministically (httpx stream against the ingress with the gated fake provider), not by timing the browser.

### Vitest live project
Use the live project for the SSE client against the real ingress (Node's global `fetch` streams in the `jsdom` environment): parse a real stream, abort mid-stream, 401 purge. Keep it free of OpenRouter calls (point the assistant at the loopback fake provider as Phase 4 live tests do for embeddings) except one gated real test inside the budget.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard control |
|---------------|---------|------------------|
| V2 Authentication | yes (existing) | Auth gate and tokens from Phase 2; SSE sends the same Bearer header; 401 purge path |
| V3 Session Management | yes | Chat sessions are per user; session ids are 32-hex and any miss is the one 404 |
| V4 Access Control | yes | Object-level rules (`me`/`team`, per-user sessions, dataset visibility) in services; cross-tenant matrix invokers for every new row (D-19) |
| V5 Input Validation | yes | pydantic bodies with `extra=forbid`, length caps, id regexes, tokenised query text only (no user text reaches Elasticsearch syntax); filter keys regex-checked |
| V6 Cryptography | no new | Provider keys stay sealed (R-137); no new crypto |
| V7 Error handling and logging | yes | Redacting logger; no question text or chunk text in logs; machine reasons in `data.reason` |
| V8 Data protection | yes | Read-time redaction of references; private dataset text never returned to others |
| V11 Business logic | yes | Rate limit and turn lock; caps on session size and context size |
| V13 API | yes | Typed errors, envelope on every pre-stream failure, content-type check on the client |

### Known Threat Patterns

| Pattern | STRIDE | Standard mitigation |
|---------|--------|---------------------|
| Cross-tenant retrieval via foreign dataset ids | Information disclosure | Index per tenant (`ragflow_{tenant}`) + mandatory `kb_id` terms filter; foreign id is 404 for the whole request; docstore-level test (tenant A index + tenant B id returns zero hits) |
| IDOR on assistants and sessions | Elevation | Visibility helpers; teammate's session id is the same 404 as a random one |
| Stale reference exposes a later-private dataset | Information disclosure | Read-time visibility check and redaction |
| Indirect prompt injection in retrieved chunks | Tampering | Delimited knowledge blocks, "treat as data" instruction, no tools in this phase, canonical output only, links restricted to `#cite-N` and normal markdown links |
| Markdown/HTML injection in answers | Tampering / XSS | react-markdown without raw HTML; default URL sanitising; no `dangerouslySetInnerHTML` |
| Elasticsearch query injection | Tampering | Tokenised terms only, `simple_query_string` flags limited to `AND|OR|PHRASE|PREFIX` (BE-06), field names regex-checked |
| SSRF through rerank base URL | Information disclosure | `url_guard`; TEI default skipped by exact match only; OpenRouter default skipped |
| Provider key leakage | Information disclosure | Key never in logs, responses, frames or error text; leak scan of all recorded responses and app logs (R-147 method); new routes added to the sweep |
| Spend exhaustion / DoS via completions | Denial of service | Per-user rate limit, turn lock, question and context caps, stream deadline, `max_tokens` clamp |
| Resource exhaustion from huge rerank payloads | Denial of service | Rerank cap, batch size 32, per-batch timeout, token truncation |
| Replay of a stale stream after logout | Spoofing | A 401 mid-session purges; the stream carries no long-lived secret |

## Risk List

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| R1 | 8B model does not emit usable `##N$$` | medium | gate fails on D-07 | Prompt example, CHAT-19 fallback, probe and switch rule to `gpt-4o-mini` |
| R2 | TEI crashes or is slow on this CPU | medium | criterion 4 blocked | Smoke task first; `MKL_ENABLE_INSTRUCTIONS=AVX2`; smaller `rerank_max_candidates`; OpenRouter rerank as the second path (D-02) |
| R3 | Disk (14 GB free) or RAM (7.8 GiB available) exhausted by TEI | medium | stack unstable | Measure; volume size recorded; preflight threshold; `mem_limit` from measurement |
| R4 | Quart streams truncated at 60 s | high if unhandled | answers cut | `response.timeout`, test |
| R5 | Threshold semantics make the empty path unreachable or too eager | medium | criterion 3 flaky | Cosine mapping and calibration |
| R6 | Recall on large corpora (text-only matches fall below kNN) | low now | quality | Documented; `limit = top_k`; revisit when real corpora exist |
| R7 | Leak-sweep or matrix extensions forgotten | high (happened in Phase 4) | gate fails late | Make invokers part of each route plan's definition of done |
| R8 | Package checkpoint declined or slow | medium | UI blocked | Hand-written SSE parser fallback; GFM-less markdown fallback is plain text with line breaks |
| R9 | Stop leaves the turn lock or a half-written message | medium | stuck sessions | `finally` release with TTL as backstop; test |
| R10 | Provider-reported usage absent on abandoned streams | certain | undercount | Estimate on stop (Open Question 4) |
| R11 | Phase 4 clean-room gate still deferred (B-36) | n/a | Phase 5 gate runs on an unproven base | Record in Phase 5 verification; do not claim the clean-room pass |
| R12 | Coarse PDF boxes (R-190) make the highlight imprecise | known | UX only | Not a Phase 5 defect; drawer shows the chunk text as well |
| R13 | Multi-turn follow-ups retrieve poorly (last user message only) | medium | UX | Partial by D-12; state it in the UI help text and the Partial row |

## Proposed Decision Rows (next free IDs: R-192, B-37)

| Topic | Proposed resolution |
|-------|--------------------|
| R-26 (close) | Delta frames, canonical final frame with reference, `[DONE]`; stop = client abort, server persists partial in `finally`; `response.timeout` set; pre-stream failures are normal HTTP errors |
| R-27 (refine) | 0-based index into the prompt's chunk list; canonicalisation and fallback rules in Pattern 4 |
| R-52 (close, after timing) | `retrieval.rerank_max_candidates` and TEI `mem_limit` from the measurement; pool stays `top_k = 1024` |
| Retrieval route | `POST /api/v1/datasets/search` (Python); Go `searchbots/retrieval_test` stays the Phase 8 beta-token surface; legacy `/v1/api/retrieval` not served (R-25) |
| Similarity semantics | Cosine mapped from ES score; kNN floor 0.0; threshold on the blended score; term similarity uniform overlap |
| Query building | `simple_query_string`, plain tokens, stopwords, synonym OR tokens, `minimum_should_match` 30 percent with a 10 percent retry; RETR-03 Partial |
| TEI | Upstream image `cpu-1.9.4` + volume, profile `tei-cpu`, model `BAAI/bge-reranker-base`, no Dockerfile_tei, sixth provider row `TEI` and `rerank` type |
| Assistant schema | Migration `0003`: `dialog.created_by`, `dialog.permission`; `finish` field on messages; reference inside the message; `Conversation.reference` unused |
| Chat permissions | Registry roles, no new matrix area; `datasets.retrieval_test` for the search route |
| Unavailable datasets | Exclude with a notice; none left is 409 `datasets_unavailable`; read-time redaction of stored references |
| Rerank failure | Fail closed (502 `rerank_unavailable`) |
| Packages | Outcome of the checkpoint |
| Partial rows | RETR-03, 04, 09, 13, 16, CHAT-05, LLM-09, ING-21, UI-22 with hand-offs |
| R-149 amendment | Estimated usage recorded on stop (if approved) |

## Sources

### Primary (HIGH confidence)
- Repo: `common/doc_store/doc_store_base.py`, `rag/utils/es_conn.py`, `rag/utils/es_mapping.py`, `rag/svr/chunk_doc.py`, `rag/llm/{chat_model,stream,__init__}.py`, `api/db/services/{llm_service,tenant_scope,tenant_model_service,chunk_service,knowledgebase_service}.py`, `api/db/models/{chat,llm}.py`, `api/apps/{__init__,middleware}.py`, `api/apps/restful_apis/{page_api,parse_api}.py`, `api/utils/blocking.py`, `conf/routes.yaml`, `conf/permissions.yaml`, `docker/docker-compose*.yml`, `docker/nginx/*`, `test/testcases/{_leak_sweep,test_phase3_isolation}.py`, `test/helpers/*`, `web/package.json`, `web/src/{services/http.ts,components/document-preview,constants/app-paths.ts}`
- Installed Quart 0.23.1 source (`.venv/.../quart/asgi.py`, `app.py`): disconnect cancellation and `RESPONSE_TIMEOUT`
- `docs/07-retrieval/*`, `docs/12-chat/*`, `docs/11-llm/{rerank-models,prompt-management,llm-request-flow}.md`, `docs/05-rag-pipeline/reranking.md`, `docs/21-end-to-end-flows/*`, `docs/04-api/{chat-api,endpoint-catalog}.md`, `docs/apis.md`, `docs/10-cache-and-queues/redis.md`, `docs/18-deployment/{docker,deployment-overview}.md`, `docs/02-frontend/*`
- Elasticsearch 8.11 docs: dense-vector (cosine `_score`), kNN search (`similarity` raw, union with `query`, `boost`), simple-query-string (operators, `^` only in `fields`) - elastic.co/guide/en/elasticsearch/reference/8.11/
- TEI: CLI arguments (https://huggingface.co/docs/text-embeddings-inference/cli_arguments), published OpenAPI (https://huggingface.github.io/text-embeddings-inference/openapi.json, version 1.9.4), repository README and Dockerfile (github.com/huggingface/text-embeddings-inference), ghcr.io tag list and manifest
- OpenRouter rerank API reference (https://openrouter.ai/docs/api/api-reference/rerank/submit-a-rerank-request) and the live models API (`/api/v1/models?output_modalities=rerank`, `/api/v1/embeddings/models`)
- Hugging Face model API for `BAAI/bge-reranker-base`, `BAAI/bge-reranker-v2-m3`, `Alibaba-NLP/gte-multilingual-reranker-base`
- npm registry and downloads API; eventsource-parser README (github.com/rexxars/eventsource-parser)

### Secondary (MEDIUM confidence)
- Reference implementation `/home/logan78/desktop x/ragflow` @ `6677f14`: `rag/nlp/{search,query,synonym}.py`, `rag/llm/rerank_model.py`, `api/db/services/{dialog_service,conversation_service}.py`, `api/apps/restful_apis/{chat_api,dataset_api}.py`, `rag/prompts/*` (supporting evidence only; docs win)
- Web search result quoting TEI release notes on the MKL regression in cpu images 1.7.0 to 1.8.1 (fixed 1.8.2)

### Tertiary (LOW confidence)
- None used for a recommendation; unverified items are in the Assumptions Log.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH for existing pieces and the npm/TEI/OpenRouter facts (verified live); MEDIUM for TEI behaviour on this CPU (assumed, smoke-tested first).
- Architecture: HIGH for SSE, Quart cancellation, ES scoring and adapter gaps (read from source and docs); MEDIUM for the exact scoring defaults (calibration task).
- Pitfalls: HIGH for those found in code or docs; MEDIUM for model-behaviour pitfalls.

**Research date:** 2026-10-19
**Valid until:** 2026-11-02 (fast-moving: OpenRouter model list and prices, TEI and npm releases; re-check tags and pins at the package checkpoint)
