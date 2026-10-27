# Phase 5 execution history — automated gate complete 2026-10-27

Plans 01–14 and 16–24 are complete. Plans 15 and 25–28 remain open. Nothing is staged or committed.

## Verified before this resume

- Python unit suite: 2348 passed, 6 existing skips (73.09 s).
- Frontend unit suite: 2136 passed across 105 files (205.26 s).
- Real-ingress SSE Vitest: 4 passed (31.13 s), local provider only.
- Deterministic Chrome chat/retrieval: 4 passed (65.57 s).
- Sharing Chrome journeys: 5 passed (37.92 s) after fixing initial workspace resolution clearing the chat/session deep link. The regression and all 19 chat-page tests pass. The app image includes this fix.
- CI: 7/7 passed before this resume.
- Phase 5 live gate: no provider calls spent yet. Thirteen tests implemented; setup uses the actual seven-chunk corpus and retrieval `size` field. The browser live test observes answer text rather than the loading placeholder and checks the full answer after reload.

## Reranker evidence

- Original BGE: 8/8 quality checks pass. Original p95 for 16 long pairs: 13.1678 s. Four-CPU quota plus 1024-token warmup: p95 14.9626 s, peak 2234.37 MiB. Four physical performance cores: p95 8.3011 s, peak 2213.89 MiB. All exceed the 5 s target.
- MiniLM: full timing matrix completed; cap 16 meets timing, but semantic reorder fails (7/8 quality checks). Retained as rejected evidence.
- INT8 BGE export: 7/8 quality checks; answering score exceeds distractor but final blend fails.
- UINT8 export: first quality run 7/8, repeat 8/8; repeated identical inputs produced distractor scores 0.71615523 or 0.8490558 depending on server batch composition. Singleton distractor 0.8490558. Rejected as unreliable for the fixed blend proof.
- Original pinned BGE restored in configuration; dev cap is provisionally 3 GiB with four CPUs and 1024 warmup tokens, based on measured working set. Candidate cap remains unchanged because latency is unresolved. No quality assertion or blend formula changed.

## Resume environment

Temporary logs and experiment containers vanished between sessions. Database/storage containers and upstream images were also absent, but all five devrag data volumes remain. Recreating only devrag infrastructure from those volumes; unrelated projects are untouched. Available disk is now about 30 GiB. Initial preflight found 3829 MiB available against its 4096 MiB RAM threshold; this is recorded, not reported as a passing preflight.

## Remaining

Restore healthy stack; finish independent integration/browser checks; run the single bounded real-provider gate when the real BGE service is ready. B-37 remains open. Do not claim plan 15 or the phase complete, insert unmeasured R-227–231, tick requirements, or claim Phase 4 B-36 clean-room completion.

2026-10-27 recovery results: stack healthy; BGE quality 8/8 (2.97 s), retrieval API 17/17 (19.11 s), deterministic browser 9/9 (42.65 s), Go race and security lint passed. Full integration still running without failures at last check. Combined API/browser live collection selects 14 checks and now asserts the shared query-embedding ceiling. No paid gate inference yet.


2026-10-27 user decision: **Accept a ten-second limit for BGE**. This supersedes the earlier pending question/five-second limit. The full measurement matrix and all quality assertions still apply. Dev affinity is configured through optional TEI_CPUSET; this host uses physical performance cores 0,2,4,6. The example stays empty for portability.


Live attempt 1 (2026-10-27): stopped after 2 passed / 1 failed in 30.15 s. Both hard streamed TXT/PDF source checks passed. The rerank-off Quenthar-9082 turn answered that it could not find the answer and cited index 0 (wrong fact), failing the unchanged numeric-answer assertion. App usage logs independently count 3 chat turns, 6 query embeddings (including citation fallback), and 4 local TEI requests; provider save adds one chat connection test. Seven chunks were ingested. No OpenRouter rerank call or browser live turn ran. The account was cleaned by the fixture. Six deterministic real-stack regressions confirm all planted TXT facts reach generation without rerank. Under D-05 the live model is switched to openai/gpt-4o-mini for attempt 2; no prompt or citation assertion is weakened. A fixture teardown will print non-secret budget counts even if the next attempt fails. The retry is a separate measured attempt and its spend must not be hidden.

Plans 25–27 are now complete: 14 combined API/browser live checks passed on the stronger-model retry, nine deterministic browser cases passed, and R-227–229 plus summaries are written. R-230 records partial hand-offs. Paid runs must not be repeated for the final gate. Full BGE timing, broader Python E2E and final record/validation updates remain; Go race and Go integration/E2E are green.


2026-10-27 restricted-session update: plans 25–27 remain complete; 05-15/05-28 remain incomplete. Docker socket access is denied and TEI/app ports are unreachable (B-39). Asyncio self-pipe writes are denied by the execution environment (B-40). Frontend 2136/2136, build, CI 7/7, security/async lint and 172 focused Python checks pass. The full Python unit run was interrupted after repeated auth timeouts; explicit phase-exit traceability stays red for the missing plan 15 summary. All eleven recovered BGE timing rows were rendered from unchanged raw samples; the last row was not run. Three truncated commands were repaired in the 72-row validation map; final flags remain false. 05-GATE-LOG.md and 05-RESUME.md hold the current evidence and recovery steps. No paid calls or commits.

## Final status — 2026-10-27

All 28 execution summaries exist. Plans 05-15/05-28 are complete and all automated tiers pass; see 05-GATE-LOG.md for final counts and budgets. BGE timing is complete (12 rows / 60 samples), cap 16 / dev 3 GiB; B-37/B-39/B-40 resolved. Retained paid Phase 5 14 checks were not repeated; remaining Phase 3/4 live checks passed 17/17 in one invocation. Human UAT, validation approval and deferred Phase 4 B-36 remain pending. No staging, commits, requirements changes or Phase 6 advancement. Earlier entries are historical.
