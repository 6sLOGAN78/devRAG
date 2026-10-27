---
phase: 05-retrieval-and-cited-chat-core-value-gate
plan: 09
subsystem: chat-sessions
tags: [sessions, feedback, valkey, redaction, isolation]
requires:
  - phase: 05-07
    provides: "assistant visibility, dataset binding and the assistant row lock"
  - phase: 05-08
    provides: "chat route family and the isolation, matrix and leak harnesses"
provides:
  - "ChatSettings with six bounded session and turn settings"
  - "Per-user session service, message persistence, read-time reference redaction, feedback, turn lock and rate guard"
  - "Five session and feedback registry rows with HTTP routes and all three security harnesses"
affects: [05-11, 05-12, 05-19, 05-21, 05-23, 05-27]
tech-stack:
  added: []
  patterns:
    - "Session queries filter both assistant and caller id"
    - "Assistant and session writes share row locks with their competing operations"
key-files:
  created:
    - api/db/services/conversation_service.py
    - api/db/services/conversation_redaction.py
    - api/apps/restful_apis/chat_session_api.py
    - test/integration/test_conversation_service.py
    - test/testcases/test_chat_session_flow.py
  modified:
    - common/settings.py
    - conf/service_conf.yaml.template
    - docker/.env.example
    - docker/docker-compose.yml
    - conf/routes.yaml
    - test/testcases/test_phase3_isolation.py
    - test/testcases/_matrix_fixtures.py
    - test/testcases/test_response_leaks.py
    - .planning/DECISIONS.md
key-decisions:
  - "R-212 records per-user session ownership, read-time redaction, turn lock and rate guard, feedback and ChatSettings bounds"
patterns-established:
  - "Read-time session views use an explicit public field list for messages and reference chunks"
requirements-completed: []
duration: resumed across sessions
completed: 2026-10-25
---

# Phase 5 Plan 09: Private Chat Sessions

Each member now has private sessions on assistants they can open. Session reads page messages in chronological order and recheck every referenced dataset for the current reader. Feedback applies only to a completed assistant message in the caller's own session. Valkey guards turns and rate limits with TTLs and fails closed when unavailable.

## Tasks and verification

| Task | Result |
|------|--------|
| 1. ChatSettings and conversation service | Six bounded settings, session and message operations, row lock, redaction, feedback, turn lock and rate guard; 33 integration cases passed |
| 2. Routes and HTTP flow | Five registry rows, sibling blueprint, generated route files and OpenAPI snapshot; 18 session e2e cases passed |
| 3. Security harnesses and R-212 | Isolation invokers, matrix builders with session snapshots, leak sweep and decision row; combined e2e suite passed |

The rebuilt stack passed `scripts/wait_stack.sh`. The combined session, isolation, matrix and leak run passed 276 e2e cases; after final response filtering, 20 focused session/OpenAPI e2e cases passed. Settings, env catalog, layering and phase-record tests passed 158 cases. The conversation service passed 33 integration cases, including lock ownership and TTL, store outage, assistant row lock, message cap, feedback and dataset redaction. `gen_routes.py --check`, generated-file checks, Ruff, `git diff --check` and all 7 CI gates passed.

## Notes

The plan calls these “six routes,” while its listed GET/POST session collection, GET/DELETE session detail and POST feedback methods total five registry rows. All five listed methods were implemented and covered. The matrix request helper omits empty JSON objects; its session setup now sends a valid name. An overnight environment reset stopped the stack, which was restarted without clearing its volumes.

Plan 05-10 can use the stored message and reference shapes. Changes remain uncommitted under the plan's explicit `do not commit` instruction. Phase requirements remain unticked pending phase verification.
