# Deferred items (phase 04)

## test/testcases/test_phase3_isolation.py guard tests fail (found in plan 04-18)

`test_every_phase3_row_has_an_invoker` and `test_the_guard_fails_a_row_without_an_invoker_and_an_invoker_without_a_row` (marked `unit`, run with
`pytest -m unit`, not part of `test/unit_test`) fail because Phase 4 rows under `/api/v1/datasets` have no entry in `INVOKERS`:
`POST .../documents/parse` (04-14), `GET` and `PATCH .../documents/{doc_id}` (04-16), `POST .../documents/batch-update-status` (04-17) and, since
04-18, the three `.../documents/{doc_id}/chunks` rows. Out of scope for 04-18 (it predates this plan); the cross-tenant matrix and the leak sweep
cover all of these rows. A later plan should add invokers (or narrow `PHASE3_PREFIXES`).
