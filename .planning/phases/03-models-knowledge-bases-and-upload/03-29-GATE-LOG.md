# 03-29 gate log

Append-only progress record so a later agent can resume. No secrets, only PASS/FAIL lines and durations.
A gate interrupted by a host restart must be restarted from run 1.

- 2026-10-10 04:58Z pre-fix (deferred item 5): `test_without_the_key_the_live_tier_fails_and_does_not_skip` waited 120 s for the stack (session fixture `ingress` ran before the module fixture `live_env`). Fixed by a module-scoped `ingress` override in `test/testcases/test_live_models.py` that lists `live_env` first. Proof with the stack down: guard test passes in 1 s (was 121 s fail); `uv run python run_tests.py -m unit` = 1811 passed, 1 skipped, 0 failed, 43.7 s wall.
- 23:26Z Task 1: test/unit_test/test_phase3_traceability.py committed; 5 pass + 1 PHASE3_GATE-guarded summary test; gen_routes --check ok; ci/run_all 7/7.
- 23:26Z pre-gate: preflight PASS (key present, map-count override, RAM 7231 MB, disk 17.0 GB, port 8088)
- 23:27Z pre-gate: ci/run_all 7/7, gen_routes --check, go vet + common tests, web typecheck, vitest unit (56 files, 1135 tests, 26.8 s), web build, PHASE3_GATE=1 traceability 6 passed: all PASS
- 23:27Z GATE ATTEMPT 1 started (log in scratchpad gate1.log)
- 23:39Z GATE ATTEMPT 1 run 1 FAILED at step go-tiers (after PASS unit, integration, e2e, e2e-serial, live-model, go-race): Go cross-tenant matrix (internal/e2e) has no fixture builder / isolation check for 17 Phase 3 registry rows. Fixing at source.
- 23:41Z FIX committed: fix(03-19) Go cross-tenant matrix scoped to owner:go rows (R-153); full go-tiers command then run by hand against the live stack: all ok. Restarting the WHOLE gate from run 1 (attempt 2).
- 23:41Z GATE ATTEMPT 2 started from run 1 (gate2.log)
- 23:53Z GATE ATTEMPT 2 run 1 FAILED at step live-model (PASS project-guard stop preflight up wait_stack[61s] unit integration e2e e2e-serial): PUT /api/v1/providers returned 504 in the live tier (6 setup errors). Investigating cause (attempt 1 passed this step).
- 23:53Z cause: app log shows embedding call OpenRouter baai/bge-m3 code=ERROR_TIMEOUT at the 30 s embedding timeout -> product answered provider_timeout (504). Two direct timed calls straight after returned 200 in 1.9 s each: transient provider latency, not a product defect and nothing to loosen. No code change. Restarting whole gate (attempt 3) from run 1.
- 00:03Z GATE ATTEMPT 3 run 1 FAILED at step e2e: test/testcases/test_auth_flow.py::test_tampered_and_foreign_tokens_are_401_on_python. Reading its output.
- 00:05Z cause: test defect, not product: the tampered token flipped the LAST base64 char of the HMAC signature (2 padding bits itsdangerous ignores) so it stayed valid ~7 % of the time (measured 7.2 % over 2000 tokens). FIXED: fix(02-14) test_auth_flow flips the first signature char; fix(03-02) test_secretbox same latent pattern (1 %). Both verified 0 accepted over 3000. Restarting whole gate (attempt 4) from run 1.
