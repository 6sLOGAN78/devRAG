---
phase: 05-retrieval-and-cited-chat-core-value-gate
plan: 08
subsystem: chat-api
tags: [assistants, routes, nginx, isolation, e2e]
requires:
  - phase: 05-07
    provides: "assistant service, visibility and sharing rules"
provides:
  - "Five /api/v1/chats assistant routes with typed request and response models"
  - "Generated registry, Nginx and web route entries for chat families"
  - "Live assistant flow, isolation, cross-tenant matrix and response leak coverage"
affects: [05-09, 05-11, 05-19, 05-27]
tech-stack:
  added: []
  patterns:
    - "Route handlers delegate assistant rules to dialog_service and preserve invisible-resource 404s"
    - "Every chat registry row has isolation, matrix and leak-sweep coverage"
key-files:
  created:
    - api/apps/restful_apis/chat_api.py
    - test/testcases/test_chat_assistant_flow.py
  modified:
    - conf/routes.yaml
    - docker/nginx/ragflow.conf
    - docker/nginx/ragflow.https.conf
    - test/testcases/test_phase3_isolation.py
    - test/testcases/_matrix_fixtures.py
    - test/testcases/test_response_leaks.py
    - .planning/DECISIONS.md
key-decisions:
  - "R-211 records registry roles, the three 1 MiB Nginx families, paging, delete shape and dataset-not-found mapping"
patterns-established:
  - "A new assistant route joins all three security harnesses in the same plan"
requirements-completed: []
duration: resumed across sessions
completed: 2026-10-24
---

# Phase 5 Plan 08: Assistant HTTP Routes

Members can create, list, read, update and delete assistants through `/api/v1/chats`. The routes preserve the service's private-assistant 404, team-management 403 and typed validation and conflict responses. Generated Nginx families cap request bodies at 1 MiB.

## Tasks and evidence

| Task | Result |
|------|--------|
| 1. Routes, registry and Nginx | Five assistant rows and three chat families; committed as `7f013ec` |
| 2. Real-stack assistant flow | 32 e2e cases passed; committed as `14e3954` |
| 3. Isolation, matrix, leak sweep and R-211 | Added to all three harnesses; 231 combined e2e cases passed; edits remain uncommitted under the plan's `do not commit` instruction |

The rebuilt `devrag-app:local` stack passed `scripts/wait_stack.sh`. Live checks: 32 assistant-flow tests, 231 isolation/matrix/leak/OpenAPI tests, 14 Nginx integration tests, and 3 phase-record unit tests. `gen_routes.py --check`, `check_generated.py`, `check_decisions.py`, `check_no_sleep.py` and all 7 CI gates passed. The web unit suite passed 1705 tests with one worker and `npm run build` passed earlier in the session.

## Deviations and issues

Docker access was unavailable in the earlier session. Once available, the first image build ended before export under heavy host memory pressure. Stopping the devRAG Elasticsearch and task worker during the retry freed memory; the retry built successfully. The full Python unit suite had an intermittent auth lookup timeout under host load in an earlier offline run; the isolated case passed. The required 05-08 live suites are green.

## Next plan

Plan 05-09 can add per-user sessions and session routes using the assistant service and the registry coverage pattern established here. Phase requirements remain unticked pending phase verification.
