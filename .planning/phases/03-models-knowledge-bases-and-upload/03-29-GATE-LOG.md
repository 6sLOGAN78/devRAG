# 03-29 gate log

Append-only progress record so a later agent can resume. No secrets, only PASS/FAIL lines and durations.
A gate interrupted by a host restart must be restarted from run 1.

- 2026-10-10 04:58Z pre-fix (deferred item 5): `test_without_the_key_the_live_tier_fails_and_does_not_skip` waited 120 s for the stack (session fixture `ingress` ran before the module fixture `live_env`). Fixed by a module-scoped `ingress` override in `test/testcases/test_live_models.py` that lists `live_env` first. Proof with the stack down: guard test passes in 1 s (was 121 s fail); `uv run python run_tests.py -m unit` = 1811 passed, 1 skipped, 0 failed, 43.7 s wall.
