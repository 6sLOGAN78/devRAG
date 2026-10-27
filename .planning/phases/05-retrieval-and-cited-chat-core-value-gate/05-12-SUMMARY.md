---
phase: 05-retrieval-and-cited-chat-core-value-gate
plan: 12
subsystem: chat-streaming
tags: [sse, cancellation, nginx, usage, citations]
requires:
  - phase: 05-11
    provides: "Stored cited turn and completion route"
provides:
  - "SSE deltas, final frame and terminator over the completion route"
  - "Cancellation and timeout persistence with estimated usage"
  - "Ingress proof of unbuffered first-frame delivery and stopped turns"
affects: [05-13, 05-16, 05-17, 05-25]
tech-stack:
  added: []
  patterns:
    - "Preflight before Response for HTTP refusals, then stream frames"
    - "Cancellation-safe DB_EXECUTOR.submit for abandoned turns"
key-files:
  created:
    - api/apps/sse_frames.py
    - test/unit_test/test_sse_frames.py
    - test/integration/test_completion_stream_app.py
    - test/testcases/test_chat_stream_nginx.py
  modified:
    - api/apps/restful_apis/completion_api.py
    - api/db/services/chat_turn_service.py
    - docker/nginx/proxy.conf
    - test/testcases/test_chat_flow.py
    - test/testcases/test_response_leaks.py
    - test/helpers/fake_provider.py
    - .planning/DECISIONS.md
key-decisions:
  - "R-215 records deadline, stop persistence and ingress behaviour"
requirements-completed: []
duration: resumed across sessions
completed: 2026-10-26
---

# Phase 5 Plan 12: Streaming Cited Answers

The completion route accepts `stream=true` and sends SSE delta frames, one final canonical answer with references, and `[DONE]`. It prepares and authorises the turn before building the response. It persists the final answer before the final frame, stores a failed turn and error frame after a provider failure, and schedules partial persistence when a client disconnects. Partial references retain only cited chunks and their original indices; estimated usage is stored and charged. Provider reads have an application deadline slightly inside Quart's response deadline so a held stream settles cleanly.

Nginx passes `X-Accel-Buffering: no` to clients while keeping proxy buffering off. The ingress tests prove a first frame arrives while the provider is held, a client abort stores a stopped turn and releases its lock, a sparse `##2$$` citation remains index 2, estimated usage reaches `used_tokens`, and a 12 KiB answer arrives in multiple network reads.

## Verification

- Chat and ingress e2e: 32 passed (26 chat flow cases and 6 ingress cases).
- Quart streaming integration: 4 passed, covering response timeout override, pre-byte JSON refusal, stop before the first provider token and a held-provider deadline.
- SSE, layering and decision unit tests: 18 passed; the fake provider chat suite also passed.
- Response leak sweep: 6 passed with a complete stream scanned.
- Route generation check, Ruff, `git diff --check` and all 7 CI gates passed.

Changes remain uncommitted under the plan's `do not commit` instruction. Phase requirements remain unticked pending phase verification.
