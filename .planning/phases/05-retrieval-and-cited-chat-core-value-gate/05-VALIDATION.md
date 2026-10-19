---
phase: 5
slug: retrieval-and-cited-chat-core-value-gate
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-10-19
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `05-RESEARCH.md`, section "Validation Architecture". The planner fills in the task IDs in the per-task map.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 + pytest-asyncio (auto) + pytest-timeout (`filterwarnings=error`); vitest (`unit` and `live` projects); real headless Chrome via `test/helpers/chrome_cdp.py` |
| **Config file** | `pyproject.toml` (markers `unit`, `integration`, `e2e`, `serial`, `smoke`, `live_model`), `run_tests.py`, `web/vitest.config.ts`, `scripts/clean_room.sh` |
| **Quick run command** | `uv run python run_tests.py -m unit` and `cd web && npx vitest run --project unit` |
| **Full suite command** | `uv run python run_tests.py -m integration`; `-m "e2e and not serial"`; `-m "e2e and serial"`; `-m live_model`; `cd web && npx vitest run --project live`; `uv run python scripts/ci/run_all.py` |
| **Estimated runtime** | unit ~70 s, web unit ~50 s; integration ~10 min; e2e ~10 min; live ~3 min |

Use `uv run python -m pytest` (the venv `pytest` script has a stale shebang). Pipe-to-tail verifies use `(set -o pipefail; ...)`. No fixed sleeps (`no_sleep` gate): use `waitUntil` / deadline polling.

---

## Sampling Rate

- **After every task commit:** unit tier, plus the one integration file touched; vitest for the web files touched.
- **After every plan wave:** `-m integration`, `scripts/ci/run_all.py`, `npx vitest run --project unit`.
- **Before `/gsd:verify-work`:** e2e, serial, live_model, vitest live and the real-Chrome criterion-5 journey must all be green.
- **Max feedback latency:** 120 seconds per task (stack rebuilds excluded).

---

## Phase Requirements to Test Map (from research)

| Req | Behaviour | Type | Command | Exists |
|-----|-----------|------|---------|--------|
| RETR-06, 14, 15 | golden `fuse`, threshold, pagination; swapped weights fail | unit | `pytest test/unit_test/test_fusion_golden.py -q` | Wave 0 |
| RETR-07 | RRF numbers | unit | `pytest test/unit_test/test_rrf.py -q` | Wave 0 |
| RETR-02, 03, 04 | query builder, stopwords, synonyms, escaping | unit | `pytest test/unit_test/test_query_builder.py -q` | Wave 0 |
| RETR-19 | NaN/Inf to null | unit | `pytest test/unit_test/test_sanitize_floats.py -q` | Wave 0 |
| LLM-09 | `normalize_rank`, driver parsing, batching, error mapping | unit | `pytest test/unit_test/test_rerank_model.py -q` | Wave 0 |
| RETR-01, 05, 08, 10, 12, TEN-03 | fusion order, filters, pruned docs, foreign dataset id returns nothing | integration (real ES) | `pytest -m integration test/integration/test_retrieval_es.py -q` | Wave 0 |
| DEPLOY-18, LLM-09, RETR-11 | TEI health, `/rerank` order, batch 32, truncate | integration (real TEI) | `pytest -m integration test/integration/test_rerank_tei.py -q` | Wave 0 |
| CHAT-01..11, D-08..D-11 | assistant CRUD, visibility, binding rules, per-user sessions | integration | `pytest -m integration test/integration/test_dialog_service.py test/integration/test_conversation_service.py -q` | Wave 0 |
| CHAT-16..19, R-27 | context builder, trimming, marker normalisation, fallback | unit | `pytest test/unit_test/test_prompt_context.py test/unit_test/test_citations.py -q` | Wave 0 |
| CHAT-12, 13, 21, 22, R-26 | frame shape, `[DONE]`, final replace, stop persistence, timeout | e2e | `pytest -m e2e test/testcases/test_chat_flow.py -q` | Wave 0 |
| DEPLOY-18 Nginx | first frame before last through ingress | e2e | `pytest -m e2e test/testcases/test_chat_stream_nginx.py -q` | Wave 0 |
| D-19 isolation | invokers, matrix, leak sweep for every new route | e2e | `pytest -m e2e test/testcases/test_phase3_isolation.py test/testcases/test_cross_tenant_matrix.py test/testcases/test_response_leaks.py -q` | extend |
| RETR-18, KB-18, E2E-07 | retrieval-test route on the real stack | e2e | `pytest -m e2e test/testcases/test_retrieval_flow.py -q` | Wave 0 |
| CHAT-20, D-15 | empty response with zero model calls | e2e | in `test_chat_flow.py` | Wave 0 |
| D-07, CHAT-18, E2E-08 | planted facts cite the planted chunk | live_model | `pytest -m live_model test/testcases/test_live_chat.py -q` | Wave 0 |
| RETR-11 criterion 4 | real rerank reorders a crafted case | live + integration | `test_rerank_tei.py`, `test_live_chat.py` | Wave 0 |
| UI-05 | SSE parser: split chunks, CRLF, comments, `[DONE]`, abort | vitest unit | `npx vitest run --project unit src/services/sse.test.ts` | Wave 0 |
| UI-18, 20..25 | retrieval test, message list, stop, markdown safety, pills, drawer, settings | vitest unit | `npx vitest run --project unit` | Wave 0 |
| E2E-09, E2E-12, criterion 5 | register to cited streamed answer, drawer highlight, refresh keeps turn | real Chrome + live | `pytest -m "e2e and live_model" test/testcases/test_spa_chat_browser.py -q` | Wave 0 |
| UI live | SSE client against the real ingress | vitest live | `npx vitest run --project live src/pages/chat/chat.live.test.ts` | Wave 0 |

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (planner fills) | | | | | | | | | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] The new test files in the map above, written first (D-21).
- [ ] `test/helpers/fake_provider.py`: a gated or delayed chat stream and a record of chat requests (first-frame-before-last, stop, "no model call on empty").
- [ ] Controlled-vector fixtures through `test/helpers/doc_store_contract.py` for the golden fusion integration test.
- [ ] Planted-fact corpus: a 6-paragraph TXT (one rare fact each) and a 3-page PDF from `text_pdf` with one fact per page.
- [ ] One-off probe tasks, outside the gate budget: TEI smoke and timing on this CPU (R-52); `tsim`/cosine/`sim` calibration with real `bge-m3` (about 20 embedding calls); 8B citation adherence (15 chat calls, switch rule in research Pattern 4).

---

## Live Budget (D-06)

At most **15 chat turns** reach the model per gate run (planned: 9), plus about 10 query embeddings. The OpenRouter rerank driver gets at most one smoke call per run. The app counts turns from the persisted messages and the test keeps its own counter; both are asserted.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Citation highlight sits on the cited text | UI-24 (drawer), D-13 | Tests assert the box is inside the page image, not that it covers the right words (same limit as Phase 4 R-190) | Open the drawer from a PDF citation; check the highlight covers the sentence with the planted fact |
| Chinese draft copy for chat and retrieval pages | UI-18, UI-20..25 | No Chinese reader in the loop (B-18) | Review `web/src/locales/areas/zh/` files added in Phase 5 |
| Answer quality beyond planted facts | Core value | Planted facts prove citation correctness, not general answer quality | Ask two free-form questions on a real document and judge the answers |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120 s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
