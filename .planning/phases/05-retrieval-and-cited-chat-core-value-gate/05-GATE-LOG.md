# Phase 5 automated gate — PASS, human review pending

Completed 2026-10-27. Plans 05-15 and 05-28 are complete; all 28 execution summaries exist. All automated tiers pass on the existing stack. Manual UAT and final validation approval remain pending. B-36 Phase 4 clean-room verification was **not run and is not claimed**. Nothing was staged or committed, no requirement checkbox changed, and Phase 6 was not started.

## Final command results

Python commands below used `UV_CACHE_DIR=/tmp/devrag-uv-cache uv run --no-sync python` because the virtualenv activation script still points at the former checkout. Host test clients used `taskset -c 8-15`; no test assertion or application deadline was changed to accommodate that environment. Database tiers ran sequentially after the fixes. Unchanged frontend evidence and the paid Phase 5 result are retained from the preceding gate segment; this is a resumed gate, not a claim that every command ran in one uninterrupted process.

| Command / tier | Result | Duration / evidence |
|---|---|---|
| Compose profiles `cpu elasticsearch mail tei-cpu`, `up -d --build`; `WAIT_STACK_TIMEOUT=900 scripts/wait_stack.sh` | PASS; corrected app/worker rebuilt | `05-STACK-FINAL.log`; normal health restored again after serial |
| `PREFLIGHT_STRICT_PROJECT=1 COMPOSE_PROJECT_NAME=devrag-stack scripts/preflight.sh --project-only` | PASS | Nine existing project containers belong to this checkout |
| `python run_tests.py -m unit` | PASS: 2411 passed, six existing skips | 104.50 s; `05-UNIT-FINAL.log` |
| `cd web && npm exec --offline -- vitest run --project unit` | PASS: 2136 tests / 105 files | 51.01 s; retained unchanged-frontend result |
| `cd web && npm run build` | PASS | Vite 10.68 s; existing large-chunk warning |
| `python run_tests.py -m integration` | PASS: 905 tests | 877.07 s; `05-INTEGRATION-FINAL.log`; includes eight real-TEI cases |
| `python run_tests.py -m 'e2e and not serial and not live_model'` | PASS: 869 tests | 918.58 s; `05-E2E-FINAL.log` |
| `python run_tests.py -m 'e2e and serial and not live_model'` | PASS: 13 tests | 189.17 s; `05-E2E-SERIAL-FINAL.log` |
| Phase 5 `test_live_chat.py` plus criterion-5 paid browser selection | PASS: 14 tests | 103.52 s; retained R-227/R-228 evidence; paid cases not repeated |
| `python -m pytest -m live_model test/testcases/test_live_models.py test/testcases/test_live_ingestion.py -q -s -x` | PASS: remaining 17 tests | 76.04 s; `05-LIVE-REMAINING.log` and `.counters.json`; one invocation only |
| `cd web && npx vitest run --project live` | PASS: 61 tests / 15 files | 168.97 s; retained real-ingress/local-provider result |
| `GOMAXPROCS=2 go test -p 1 -race ./internal/...` | PASS | 1.422 s; Go package cache hits disclosed in `05-GO-RACE-FINAL.log` |
| `GOMAXPROCS=2 go test -p 1 -tags=integration,e2e ./...` | PASS | 28.781 s; DAO 8.732 s and E2E 16.563 s executed, remaining package cache hits disclosed; `05-GO-INTEGRATION-E2E-FINAL.log` |
| `python scripts/ci/run_all.py` | PASS: 7/7 gates, 231 decision rows | `05-CI-FINAL.log`; decisions, generated, Go toolchain, no-sleep, pickle, placeholders, secrets |
| `uv run --no-sync ruff check --select S,ASYNC,FIX001,FIX002 --ignore S603,S607 .` | PASS | `05-LINT-FINAL.log`; existing S403-preview selection notice only |
| `PHASE5_GATE=1 python -m pytest test/unit_test/test_phase5_records.py test/unit_test/test_phase5_traceability.py -q` | PASS: 10 tests | 0.15 s; R-192..R-231 contiguous, all required titles, 61 requirements, D-01..D-26, implemented routes and summaries through plan 27 |
| Full-profile Compose `config --quiet`; `git diff --check` | PASS | No generated/configuration drift or whitespace errors |

Go ran under bash with `SERVICE_CONF`, `E2E_BASE_URL`, `MANUAL_BASE_URL` and `MYSQL_ROOT_PASSWORD` derived as in `scripts/clean_room.sh`; credentials were not printed. Final serial restoration leaves one healthy normal worker (`INGEST_BATCH_SIZE=64`), a healthy app with `RETRIEVAL_RERANK_MAX_CANDIDATES=16`, and healthy database/storage/TEI services. No volume was deleted. The split E2E/live selections cover all 31 live tests without repeating the 14 already-paid Phase 5 cases.

## Final criteria-to-evidence map

| Criterion | Passing evidence | Human boundary |
|---|---|---|
| 1: retrieval controls and scores | `test_retrieval_testing_page_threshold_weight_and_rerank`, all 17 retrieval API checks, golden fusion unit/ES integration tests and frontend unit controls | No additional automated gap identified |
| 2: streamed chat, stop, refresh | `test_first_frame_before_last_through_ingress`, `test_stop_persists_partial_and_releases_lock`, `test_stop_keeps_the_partial_answer_and_survives_a_reload`; ordinary E2E and ingress Vitest pass | No additional automated gap identified |
| 3: citations, source drawer, empty response | `test_planted_txt_stream_with_real_tei`, `test_planted_pdf_stream_with_real_tei`, `test_off_topic_question_shows_the_configured_empty_response`; correct source passage and PDF box in paid browser | Word-level highlight alignment remains manual; screenshot is `screenshots/phase5-core-source.png` relative to this phase directory |
| 4: real rerank and isolation | Eight real-TEI integration tests including `test_reranked_order_differs_from_fusion_order`; `test_real_tei_rerank_through_the_stack`; foreign/random dataset refusal, cross-tenant matrix and leak sweep in ordinary E2E | Intended document languages and footprint fit remain user judgment |
| 5: registration to cited answer in real browser | `test_criterion_5_register_to_cited_streamed_answer`: real GPT-4o-mini, BGE-M3 and local original BGE; ten distinct nonzero streamed lengths, citation/source and reload preservation | Chinese copy and usefulness on two free-form real-document questions remain manual |

## Final live budget reconciliation

| Scope | Answer turns | Provider-save chat tests / other chat-class attempts | Total chat-class attempts | Query embeddings | External rerank requests |
|---|---:|---:|---:|---:|---:|
| Initial failed Phase 5 attempt (separately spent) | 3 | 1 | 4 | 6 | 0 |
| Successful Phase 5 API + browser retry | 9 | 2 | 11 | 13 | 2 including save probe |
| Remaining Phase 3 model tier | 2 | 2 (save + deliberate refused-key attempt) | 4 | One batch embedding plus one save embedding: two embedding calls total | 0 |
| Remaining Phase 4 ingestion tier | 0 | 0 | 0 | Four nearest-query calls in the passing test path | 0 |

**Successful whole-gate chat-class total: 15 (11 Phase 5 + 4 Phase 3). Cumulative total including the failed Phase 5 attempt: 19 (4 + 11 + 4).** A refused-key attempt is counted as an attempted request, not a claim of a billed successful generation. D-06's 15-call ceiling applies to each Phase 5 attempt; the query-embedding cap of 17 is R-227's refinement. Each Phase 5 attempt stays within its caps; the two external rerank requests include the save probe. No Phase 5 paid case was rerun during this final recovery.

Ingestion evidence is kept separate from query calls. The successful Phase 5 API fixture embedded seven chunks with two worker calls. Its separate browser PDF ingestion-call count and the complete successful local-TEI request count were not retained across worker recreation; they are explicitly unquantified, not estimated or claimed as zero. The failed initial attempt counted four local-TEI requests.

The outstanding Phase 4 live run embedded **57/72 chunks**: 50 initial chunks (26 PDF + 5 TXT + 4 DOCX + 5 XLSX + 5 PPTX + 5 HTML), two edit/add embeddings and five reparse chunks. Structured usage logs captured after serial restoration show **eight worker + two API ingestion calls** for its test tenant; the four direct nearest-query calls and one provider-save embedding probe are separate. Its scan covered 74 responses, eight progress lines and eight log rows with zero key hits. Phase 3 counters show chat 4/6 and embedding 2/3, with zero response/log key hits. `05-LIVE-REMAINING.counters.json` retains only timestamps, counts, model/provider and non-secret test identifiers.

## Host measurements and review outcome

`05-RERANK-TIMING.md` and its raw samples retain all twelve rows / sixty repetitions with mixed-run provenance. N=16 at 512 tokens has p50 6.1942 s / p95 6.2308 s, versus N=32 p95 12.3098 s. The user's approved ten-second ceiling selects **cap 16**, with `top_k=1024` unchanged. Maximum matrix/startup working-set sample 2267.136 MiB plus rounded 25% headroom selects **3 GiB** dev memory. Cached restart is 9.954 s, uncompressed image 937659489 bytes, model-cache volume 3.446 GB. The original pinned BGE ONNX digest matches the approved package audit. Shared-host load and cached-versus-first-download limits are disclosed. B-37/B-39/B-40 are resolved.

Formal inline code review is in `05-REVIEW.md`: zero open blockers/warnings, three correctness findings and one stale test expectation resolved. New failing regressions proved lease expiry between stages, a late complete write after nonstream timeout, and stale/premature ingestion roll-up. The owner-renewal, bounded-finalization and checked-current-status roll-up fixes pass affected and full tiers. The default TEI assertion now strictly expects the final configured service to succeed. No test was skipped or weakened to obtain green. The checklist below and review artifact record tenant scope, log/key hygiene, checked index updates, named executors, TTLs, generated artifacts, package approval and route coverage.

## Validation and remaining human work

The throwaway validation-map audit found **72 tasks, 71 automated commands, one approved human checkpoint (05-14-2), zero command drift and all 58 referenced Python/shell files present**. All Wave 0 fixtures/probes exist. Automated task rows are green. The two blanket validation flags remain false under plan 28's literal every-task-automated condition: the human checkpoint is not mislabeled as executable automation. Full integration/E2E/ingress/timing also exceed 120 seconds, so universal feedback latency is not claimed. These declared contract limits are recorded for orchestrator review; they do not hide a runtime failure. Final approval remains `pending`.

Follow `05-HUMAN-UAT.md` for the five outstanding checks. The automated criteria above are 5/5 supported; phase verification is **human_needed**. R-230 and ROADMAP retain the ten Partial requirements and hand-offs. `.planning/REQUIREMENTS.md` is untouched. Phase 4 B-36 stays open and Phase 6 is not advanced.

---

## Chronological execution history — earlier status snapshots

The following entries preserve interrupted/red runs and intermediate observations. Their pending/running statements are historical and superseded by the final result above.

# Phase 5 verification — in progress

This is an incremental record, not a phase-completion claim. Nothing is staged or committed. Phase 4 B-36 clean-room work is deferred and has not been run.

Entries retain earlier runs chronologically. The final "Full-access resumption" section is current; restricted-session blocks and earlier incomplete timing statements are historical. Plan 15 is now complete: twelve timing rows / sixty samples select cap 16 and dev memory 3 GiB. Final unit/integration tiers pass; final ordinary E2E is active before the serial/live tiers.

| Check | Result |
|---|---|
| Python unit suite (2026-10-26) | 2348 passed, 6 existing skips, 73.09 s |
| Frontend unit suite after cold-workspace fix | 2136 passed / 105 files, 205.26 s |
| Frontend build (2026-10-27 local date) | Passed, 10.29 s; existing large-chunk warning |
| Compose/env/rerank probe unit tests after restoring BGE | 30 passed, 0.38 s |
| Calibration probe after replacing optimization-removable assert | 16 passed, 0.03 s |
| Current CI | 7/7 gates passed |
| Security/async lint | Passed after one probe invariant fix and five explicit leak-string false-positive annotations |
| Real BGE integration in recreated compose service | 8 passed, 2.97 s |
| Retrieval API including default-address real TEI | 17 passed, 19.11 s |
| SSE client through real ingress (previous run) | 4 passed, 31.13 s; local provider |
| Entire frontend ingress project | 61 passed / 15 files, 168.97 s; local providers |
| Deterministic Chrome chat/retrieval (previous run) | 4 passed, 65.57 s |
| Sharing Chrome journeys (previous run) | 5 passed, 37.92 s |
| Recreated-stack deterministic Chrome chat/retrieval/sharing | 9 passed, 1 paid-provider case not selected, 42.65 s |
| Traceability, ordinary mode | 4 passed, 2 phase-exit checks deferred |
| Traceability, PHASE5_GATE=1 | 5 passed, 1 failed: only plan 15 summary remains missing after completing 25–27. Gate excludes its own plan 28 summary as prescribed. |
| Full integration suite, TEI checked separately | 890 passed, 3373 deselected, 823.03 s; plus the 8/8 real-TEI tests above |
| Go race (`go test -p 1 -race ./internal/...`, GOMAXPROCS=2) | Passed |
| Paid real-provider gate, attempt 2 | 14 passed, 4 deterministic cases not selected, 103.52 s; R-227/R-228 budgets |
| Go integration/e2e (`go test -p 1 -tags=integration,e2e ./...`) | Passed |

## Review checklist (partial)

- Chat route logs inspected in completion_api.py and chat_turn_service.py: identifiers and exception class only, no question, answer or provider secret. LLMBundle logs model/provider/token counts.
- Session reads are scoped to assistant and caller; assistant resolution supplies workspace authorization. Read-time references filter datasets by current openability and preserve citation indices.
- Chat turn locks expire after the configured stream deadline plus 30 seconds; chat rate-limit keys use the shared TTL limiter.
- Blocking chat preparation/finalization uses PROVIDER_EXECUTOR; storage uses DB_EXECUTOR. Stream cancellation persists a stopped partial through the executor.
- Secret, generated-file, placeholder and no-sleep gates pass in current CI.
- New source files: none over 400 lines. New chat/reference/retrieval modules have no unchecked DocStore update calls. Phase 5 routes are included in isolation/matrix/leak test invokers.
- Remaining tiers, live budgets and final validation-map sign-off remain pending.

## Open blocker and environment recovery

B-37 remains open: original BGE quality passes but even the four-performance-core guard has p95 8.3011 s versus the required 5 s. MiniLM and quantized alternatives failed the fixed quality test or repeatability. Original pinned BGE is restored; 3 GiB / four CPUs / 1024 warmup tokens remain provisional, not a final measured cap.

Missing devrag database/storage containers and upstream images were recreated from their retained named volumes. App, worker, database/storage and TEI are healthy again. No volumes were deleted. Initial preflight reported available RAM 3829 MiB below its 4096 MiB threshold; that preflight is not claimed passed. Disk is above the 6 GiB floor.

The user has been asked whether the latency requirement may change to 10 seconds. Until answered, the 5-second requirement remains in force; elapsed time or a default selection is not approval.


2026-10-27 user decision: **Accept a ten-second limit for BGE**. This supersedes the earlier pending question/five-second limit. The full measurement matrix and all quality assertions still apply. Dev affinity is configured through optional TEI_CPUSET; this host uses physical performance cores 0,2,4,6. The example stays empty for portability.


Live attempt 1 (2026-10-27): stopped after 2 passed / 1 failed in 30.15 s. Both hard streamed TXT/PDF source checks passed. The rerank-off Quenthar-9082 turn answered that it could not find the answer and cited index 0 (wrong fact), failing the unchanged numeric-answer assertion. App usage logs independently count 3 chat turns, 6 query embeddings (including citation fallback), and 4 local TEI requests; provider save adds one chat connection test. Seven chunks were ingested. No OpenRouter rerank call or browser live turn ran. The account was cleaned by the fixture. Six deterministic real-stack regressions confirm all planted TXT facts reach generation without rerank. Under D-05 the live model is switched to openai/gpt-4o-mini for attempt 2; no prompt or citation assertion is weakened. A fixture teardown will print non-secret budget counts even if the next attempt fails. The retry is a separate measured attempt and its spend must not be hidden.

Timing-run load note: ordinary local-provider E2E, frontend ingress and Go checks run concurrently on this shared host. The stronger-model live retry starts during the larger 128-token rows; these rows do not select the cap (only 512-token rows do). Its small TEI requests may contribute queue time to those short-input throughput figures. No measurement is described as an isolated-machine benchmark.

Final pre-timing records check: 230 contiguous decisions, four records tests pass; CI 7/7 and security/async lint pass. No newly introduced source file exceeds 400 lines. Validation map audit: 72 plan tasks and 72 map rows, no missing/extra task IDs; plan 14 task 2 is the explicit human approval checkpoint. Final status flags remain false until the remaining timing and gate tasks finish.

Execution correction: the serial E2E tier was mistakenly launched while ordinary E2E was active. It was interrupted immediately on discovery, before a serial case completed (4266 deselected; KeyboardInterrupt at wait.py, 10.05 s). Its fixture restarted Redis. Ordinary E2E continues; any affected failures must be rerun after restoration. The serial tier will be rerun only after ordinary E2E ends. This interrupted attempt is not a pass.

2026-10-27 resume: prior timing/E2E processes are no longer alive and their /tmp logs are absent. Eleven complete timing rows survived, including 512-token N=16 p95 6.2308 s and N=32 p95 12.3098 s. The final 1024x512 row is recovered separately with five fresh repetitions and per-repetition durable checkpoints; report provenance will distinguish the runs. Cached restart time is remeasured. Stopped MySQL/ES/Redis/MinIO services were started with retained volumes. Ordinary and serial E2E have no completed result and must run again. The measured 16-candidate default is applied before rebuilding for that gate: settings regression first failed (expected 16, got 64). Nothing is staged or committed.

## Restricted-session recovery — 2026-10-27

**Gate remains incomplete.** The final timing-row recovery described in the preceding entry has no completed result. Docker access is denied and both local TEI/app HTTP probes fail in this execution environment (B-39). A separate minimal asyncio probe proves that worker-thread wakeups fail at `selector_events.py:_write_to_self` with `PermissionError: [Errno 1] Operation not permitted` (B-40). Neither condition was worked around by changing product behavior or test expectations. The full unit run was interrupted after repeated auth timeouts; a focused reproduction has 1 failed / 2 passed (5.86 s), with 503 instead of the expected 404 for an authenticated unknown path.

| Command / check in this session | Result |
|---|---|
| `UV_CACHE_DIR=/tmp/devrag-uv-cache uv run --no-sync python run_tests.py -m unit` | INCOMPLETE: interrupted after repeated executor wakeup timeouts; B-40. Collection: 2417 selected / 1862 deselected. No new full-unit pass claimed. |
| `cd web && npm exec --offline -- vitest run --project unit` | PASS: 2136 tests / 105 files, 51.01 s. |
| `cd web && npm run build` | PASS: TypeScript and Vite build; Vite 10.68 s, existing large-chunk warning. |
| `UV_CACHE_DIR=/tmp/devrag-uv-cache uv run --no-sync python scripts/ci/run_all.py` | PASS: 7/7 gates (230 decision rows, generated, Go toolchain, no-sleep, pickle, placeholders, secrets). |
| `UV_CACHE_DIR=/tmp/devrag-uv-cache uv run --no-sync ruff check --select S,ASYNC,FIX001,FIX002 --ignore S603,S607 .` | PASS. Existing S403-preview selection notice only. |
| Focused pytest: `test_probe_rerank_timing.py`, `test_settings.py`, `test_env_catalog.py`, `test_compose_files.py`, `test_phase5_records.py`, `test_phase5_traceability.py` | PASS: 172 passed / 2 existing phase-exit-only skips, 2.07 s, ordinary mode. |
| `UV_CACHE_DIR=/tmp/devrag-uv-cache PHASE5_GATE=1 uv run --no-sync python -m pytest test/unit_test/test_phase5_traceability.py -q` | FAIL: 5 passed / 1 failed, 0.14 s; missing `05-15-SUMMARY.md`. Assertion preserved; plan 15 is incomplete. |
| Docker, TEI and app readiness | BLOCKED: Docker API permission denied; HTTP 6381 and 8088 fail to connect. Host container health cannot be inferred. |
| Final BGE 1024x512 row and cached restart | NOT RUN: B-39. Eleven saved rows retain five raw repetitions each, with p50/p95 verified against their samples. |
| Ordinary and serial E2E | NOT RUN: B-39. No completed result survived from the earlier interrupted runs. |
| Additional paid model calls | ZERO. Successful Phase 5 API/browser evidence retained. |

The effective UV cache override only places disposable cache writes under `/tmp`; `--no-sync` preserves the installed environment. The virtualenv activation script still names the old checkout, so the checks use `uv run` from the current project directory.

## Criteria-to-evidence map

These are recorded results, not fresh stack runs in the restricted session. They establish the implemented behaviors while the final overall gate remains incomplete.

| Criterion | Concrete evidence | Recorded result / limit |
|---|---|---|
| 1: retrieval controls and score semantics | `test_spa_chat_browser.py::test_retrieval_testing_page_threshold_weight_and_rerank`; `test_retrieval_flow.py::test_a_higher_threshold_returns_fewer_hits`; `test_fusion_golden.py::test_swapped_weights_do_not_match_the_golden_numbers` | Deterministic browser and 17-case retrieval API run passed; frontend controls covered by the 2136-test suite. |
| 2: streamed chat, stop and reload | `test_chat_stream_nginx.py::test_first_frame_before_last_through_ingress`, `::test_stop_persists_partial_and_releases_lock`; `test_spa_chat_browser.py::test_stop_keeps_the_partial_answer_and_survives_a_reload` | Four real-ingress SSE checks, nine deterministic browser scenes, and the paid browser journey are recorded passing. |
| 3: correct citations, source drawer, empty response | `test_live_chat.py::test_planted_txt_stream_with_real_tei`, `::test_planted_pdf_stream_with_real_tei`; `test_spa_chat_browser.py::test_off_topic_question_shows_the_configured_empty_response` | Seven API planted answers cite their source; paid PDF browser journey opens the correct passage. Screenshot: `screenshots/phase5-core-source.png`. Word-level highlight alignment remains human-only. |
| 4: real rerank and tenant isolation | `test_rerank_tei.py::test_reranked_order_differs_from_fusion_order`; `test_retrieval_flow.py::test_real_tei_rerank_through_the_stack`, `::test_a_non_member_a_foreign_dataset_and_a_random_id_all_answer_the_same_404` | Eight real-TEI and 17 retrieval API checks passed earlier. Full ordinary E2E still needs its completed result; final timing remains B-37/B-39. |
| 5: real registration-to-cited-answer browser path | `test_spa_chat_browser.py::test_criterion_5_register_to_cited_streamed_answer` | R-228: passed with real GPT-4o-mini, BGE-M3 embeddings, local BGE rerank, ten distinct nonzero streamed lengths and reload/source preservation. |

## Live budget reconciliation

| Attempt / scope | Answer turns | Provider-save chat tests | Total chat-class calls | Query embeddings | External rerank requests |
|---|---:|---:|---:|---:|---:|
| Initial Phase 5 attempt (failed; separately charged) | 3 | 1 | 4 | 6 | 0 |
| Successful Phase 5 API + browser retry | 9 | 2 | 11 | 13 | 2 including save test |
| Current restricted session | 0 | 0 | 0 | 0 | 0 |

The successful API corpus required two ingestion embedding calls for seven chunks. The browser used a separate PDF fixture; its ingestion-call total is not independently retained here. Local TEI traffic is separate from the external rerank count. The initial failed attempt counted four local TEI requests; no complete local TEI request total for the successful combined attempt survives in this log.

D-06's cap of 15 applies per Phase 5 attempt (nine planned answer turns); the query-embedding hard cap of 17 is the refinement recorded in R-227. Retries are separately recorded and are not hidden in a single per-run budget. Known Phase 5 chat-class spend across the two attempts is 15 (4 + 11).

**Whole gate live-model inventory:** the saved 14-check result covers the Phase 5 API/browser selection. No completed result for the separate Phase 3 `test_live_models.py` file appears in this gate log. That file budgets four additional chat-class calls per run; it must not be claimed as executed or added as observed spend without evidence. Recover its result or run only the outstanding file under the plan's budget. No paid Phase 5 test should be repeated by invoking the full `live_model` marker. The gate's complete total remains pending this inventory.

## Review checklist — current pass

| Item | Inspection / evidence | Outcome |
|---|---|---|
| Tenant and per-user scope | `dialog_service.py:144` resolves workspace membership and private visibility; `conversation_service.py:37` filters session/chat/user together; internal persistence at `:214` takes the server-prepared session id; `retrieval_service.py:153` authorizes dataset ids; `dialog_datasets.py:53` enforces workspace and object visibility on loaded ids. | No new finding in the reviewed paths. Id-addressed internal lookups rely on their preceding authorization; this is stated explicitly rather than claiming every SQL statement has a tenant column. |
| Logs and provider credentials | `completion_api.py:99`, `chat_turn_service.py:220`, `llm_service.py:241`/`:242` log ids, exception classes and counts; secret gate passes. | No prompt/question/chunk/answer/key logging found in reviewed new modules. |
| DocStore updates | Reviewed new chat/reference/retrieval modules for `.update(` calls. | No new DocStore update call requiring a checked result. Dictionary/Peewee updates are distinct. |
| Blocking I/O | `completion_api.py:82`/`:83`/`:113` and `chat_session_api.py:105` use named executors; `llm_service.py:279` records usage through DB_EXECUTOR. | Covered; current executor test failures reproduce environment-level self-pipe denial (B-40). |
| New Valkey TTLs | `conversation_service.py:172`: turn-lock TTL = stream deadline + 30 s; `common/ratelimit.py` uses transactional `expire(..., nx=True)`; `rag/nlp/synonym.py:115` uses `setex`. | Explicit expiry on reviewed new keys. |
| Fixed sleeps | CI `no_sleep`. | PASS. |
| Approved packages | `git diff -- web/package.json` and passing `phase5-packages.test.ts`. | Only eventsource-parser 4.1.2, react-markdown 10.1.0 and remark-gfm 4.0.1 added, as approved. |
| Generated outputs | CI generated gate includes routes, schema and generated-file checks. | PASS. |
| Route isolation, matrix and leak invokers | Existing registry-driven unit guards pass; explicit PHASE5_GATE endpoint check passes. | Runtime full E2E result still outstanding; static coverage alone is not its substitute. |
| New source file size | Enumerated untracked .py/.ts/.tsx production files and counted lines. | None over 400 lines. |
| Placeholders and secret checks | CI placeholder/secret gates. | PASS. |
| Validation map and human checks | Regenerated all 72 task IDs/commands from the plans; restored three truncated command cells; 05-HUMAN-UAT.md has five explicit checks. | Recorded prior-plan results are distinguished from fresh execution. Final flags and human approval remain pending. |

No new high-severity code finding was identified in this checklist pass. This does not close B-39/B-40 or supply missing timing/E2E evidence. R-231, plan summaries 15/28 and final validation sign-off remain pending. `05-RESUME.md` supplies the remaining sequence, including separate ordinary/serial E2E and paid-call preservation. No requirement checkbox was changed and no commit was made. Phase 4 B-36 clean-room verification was not run and is not claimed.


## Full-access resumption — 2026-10-27 (running)

Docker and local TEI/app access are restored; all devrag containers are healthy. A delayed asyncio executor probe returns 42 within its one-second deadline, so B-39/B-40 no longer reproduce. Project ownership guard passes for this checkout. TEI is the approved original BGE revision with AVX2, 1024 batch tokens, 3 GiB memory and physical cores 0,2,4,6. The final 1024x512 row is running with five per-repetition durable checkpoints. Python unit validation runs concurrently on disjoint efficiency cores 8–15. This is a shared-host benchmark; CPU affinity does not isolate memory bandwidth or unrelated services. No isolated-machine performance claim is made. The app container still carries the old cap 64; docker/.env and the source defaults already say 16, so the app must be rebuilt before final E2E.

Recovery progress: full Python unit tier passed 2411 tests, six existing skips, 1862 deselected in 93.50 s (clients pinned to cores 8–15). Stack rebuild and wait passed; app now reports RETRIEVAL_RERANK_MAX_CANDIDATES=16. TEI container id and StartedAt are byte-identical before/after rebuild, so its benchmark process was not restarted. The final timing row includes this short cached build and the following ordinary E2E workload on the shared host. Ordinary E2E runs with `e2e and not serial and not live_model`; paid Phase 5 tests are preserved, and destructive serial cases are scheduled only after ordinary completion. The live inventory contains 31 checks: 14 already-passed Phase 5 checks, six Phase 3 model checks, and eleven Phase 4 ingestion checks. Only the outstanding two files will run once after the ordinary/serial tiers, with their budgets recorded separately.

Gate review finding CR-05-01 (BLOCKER, fixed): a fixed turn-lock lease could expire while another separately bounded stage was still active. The new real Quart/MySQL/Valkey regression test_slow_finalization_keeps_the_turn_exclusive failed with a competing turn admitted. Owner-checked renewal was added after preparation, when streaming starts after the first token, and before finalization; lost owners fail closed and cannot renew a replacement owner. All 58 affected chat/session/stream integration tests now pass (105.38 s). R-212/R-215 record the refinement. Full Python unit validation is repeated after this product fix; stack chat regressions will run after rebuilding the updated app. The ordinary E2E run currently uses the preceding image, so its chat results alone do not validate this fix.

Ordinary E2E also exposed a stale plan-05-05 provider test that required the default TEI address to fail with 502 before TEI existed. Plan 05-15 now mandates a healthy real TEI service. The test now strictly requires HTTP 200, a configured keyless TEI provider, the requested rerank model and a persisted provider row; it no longer assumes that dependency is absent. A focused rerun is recorded separately. No assertion is relaxed to accept both success and failure.

Ordinary E2E recovery attempt 1 completed with 867 passed, two failed and one teardown error (1090.48 s). The provider failure is the stale absent-TEI expectation described above. The second failure exposed a real ingestion roll-up race: the document was marked finished before its chunk flags were synchronized, and the switch reapplied an old status snapshot. Three new integration regressions failed for stale state, early publication and ignoring a False index-update result. The transition now locks and reads the current status, requires a successful Elasticsearch update and publishes the final document/log state in that same transaction. An update refusal keeps the document running for a later cycle. Affected roll-up/document-switch/read integration tests are running. The retrieval test itself passed but module cleanup hit MySQL deadlock 1213 while a concurrent regression process was creating/deleting its own account fixtures. Final database tiers will run sequentially; no cleanup assertion or fixture check is skipped.

Gate review also proved nonstream finalization could overrun its configured deadline and later persist a complete answer after the caller timed out. The nonstream route now awaits an asynchronous service entry point that bounds preparation, generation, finalization and persistence through the existing named executors; the synchronous service entry point delegates through its private loop. Its new regression verifies the typed 504, failed stored message and absence of a late complete write after the delayed finalizer returns. The affected chat/session/stream integration group passes all 59 tests (106.28 s).

Full timing matrix completed: 12 rows / 60 raw repetitions, cap 16, maximum sampled matrix/startup memory 2267.136 MiB -> dev 3 GiB. Fresh final row median 447.6617 s / p95 455.8773 s; cached restart-to-health 9.954 s. Image 937659489 bytes; model volume 3.446 GB; active ONNX startup line and mixed-run provenance retained in 05-RERANK-TIMING.md / .samples.json. B-37 resolved. Final unit suite after all Python fixes passed 2411 tests with six existing skips in 104.50 s. Full fresh integration tier is running before subsequent E2E/serial/live tiers.

Fresh full integration tier after the lifecycle and roll-up fixes: **905 passed**, 3381 deselected, **877.07 s**. This includes all eight unchanged real-TEI checks, the new lease/finalization regressions and all three roll-up regressions. The rebuilt app/worker use the corrected source and cap 16. Full ordinary E2E rerun now runs alone with `e2e and not serial and not live_model` in 05-E2E-FINAL.log; serial and the outstanding 17 paid Phase 3/4 checks will follow sequentially.

Plan 15 summary is written; explicit `PHASE5_GATE=1` traceability plus records now pass **10/10** (0.14 s). This proves route/plan/summary coverage through plan 27; it does not replace the outstanding runtime suites.

Final ordinary E2E: **869 passed**, 3417 deselected, **918.58 s**. All 17 retrieval API tests, the document-switch regression scenario, route/isolation/leak invokers and deterministic Chrome scenes pass on the rebuilt corrected image. Serial E2E now runs alone. The R-231 records test was first pinned to 231 and failed as intended (two failures / two passes, missing row and title); the final row will be populated only after serial/live evidence is known.

Final serial E2E: **13 passed**, 4273 deselected, **189.17 s**. All dependency outages, worker crash/retry/cancel/reparse, scaling and TLS checks pass. Stack readiness and strict project ownership pass afterward; one normal worker is healthy with INGEST_BATCH_SIZE=64, app cap remains 16, and all other services are healthy. No volume was removed. Only the outstanding 17 Phase 3/4 live checks now run once; no Phase 5 paid case is selected.
