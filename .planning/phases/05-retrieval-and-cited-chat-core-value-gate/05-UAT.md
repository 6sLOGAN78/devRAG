---
status: partial
phase: 05-retrieval-and-cited-chat-core-value-gate
source: [05-01-SUMMARY.md, 05-02-SUMMARY.md, 05-03-SUMMARY.md, 05-04-SUMMARY.md, 05-05-SUMMARY.md, 05-06-SUMMARY.md, 05-07-SUMMARY.md, 05-08-SUMMARY.md, 05-09-SUMMARY.md, 05-10-SUMMARY.md, 05-11-SUMMARY.md, 05-12-SUMMARY.md, 05-13-SUMMARY.md, 05-14-SUMMARY.md, 05-15-SUMMARY.md, 05-16-SUMMARY.md, 05-17-SUMMARY.md, 05-18-SUMMARY.md, 05-19-SUMMARY.md, 05-20-SUMMARY.md, 05-21-SUMMARY.md, 05-22-SUMMARY.md, 05-23-SUMMARY.md, 05-24-SUMMARY.md, 05-25-SUMMARY.md, 05-26-SUMMARY.md, 05-27-SUMMARY.md, 05-28-SUMMARY.md]
started: 2026-10-27T16:12:37.687069+00:00
updated: 2026-10-27T17:14:33.457856+00:00
scope: remaining_human_verification
---

## Current Test

number: 6
name: Core-value and validation acceptance
expected: |
  Final Phase 5 sign-off remains pending with the recorded validation exceptions. B-36 remains separately deferred. User explicitly requested Phase 6 execution after delegated checks.
awaiting: final user acceptance, deferred while executing explicitly requested Phase 6

## Tests

### 1. PDF citation highlight alignment
expected: Open the [retained source screenshot](</home/logan78/desktop x/devRAG/.planning/phases/05-retrieval-and-cited-chat-core-value-gate/screenshots/phase5-core-source.png>). The highlighted rectangle should cover the sentence containing the planted lighthouse fact, and the source passage should support the cited answer. Does the highlight align with the correct sentence?
result: pass
verified_by: assistant_visual_inspection
authorization: "you can use the image yourself"
evidence: Highlight encloses both lines of the lighthouse sentence, including 52 meters above Corvane Bay, matching the displayed source passage. This establishes alignment in this retained screenshot; it is not a new live-browser run or general quality approval.

### 2. First real-document answer
expected: PDF alignment passed by assistant inspection at your request: the highlight covers both lines of the lighthouse sentence, including “52 meters above Corvane Bay,” matching the source passage. Next, in your own document-backed assistant, ask one free-form question and open its citation. Is the answer useful and supported by that passage? The app was unavailable at the last local check; report blocked if you cannot reach it.
result: pass
verified_by: user
response: "okk  pass"

### 3. Second real-document answer
expected: Ask a different free-form question about the same real document. Its answer should also be useful and supported by the cited passage.
result: pass
verified_by: user
response: "pass you can use google chrome or anything control screen and check out you self"

### 4. Chinese wording
expected: Switch to Chinese and review the assistant sharing controls, refusals, stopped-answer message, citations and retrieval-score descriptions. Wording should be natural and accurately describe the behavior.
result: pass
verified_by: assistant_delegated_review
evidence: Five actual Chrome screens inspected: Chinese sharing settings, citations/PDF preview, stopped answer, real app handling of a local-provider 400 refusal, and retrieval controls. Screens and local-only recorder summary: output/playwright/phase5-review/. No paid inference or replacement of prior real-provider quality evidence.

### 5. Local reranker footprint and language fit
expected: Review 05-RERANK-TIMING.md and 05-HUMAN-UAT.md. The approved original BGE artifact has 12 timing rows / 60 repetitions, candidate cap 16, 3 GiB container memory, 9.954 s cached restart and a 3.446 GB model cache. Confirm that this footprint and the selected model's language coverage suit your intended documents. Active-container identity needs a current read-only check before final acceptance; historical evidence alone is not a fresh runtime measurement.
result: pass
verified_by: assistant_delegated_review
evidence: Current running BGE ONNX hash matches 15b9a8c3da82eddf263df571281166e00e9308fe19d077084b642ebfcaf06d2b; TEI healthy, memory limit 3221225472 bytes, CPU quota 4 and affinity 0,2,4,6; cache 3.446 GB. Retained timing cap 16 and 60 samples unchanged. Official model card identifies English and Chinese (https://huggingface.co/BAAI/bge-reranker-base). Fit is established for that documented language scope only; no claim for other intended languages.

### 6. Core-value and validation acceptance
expected: After the preceding checks, confirm that the real document-to-answer experience meets your needs and that you accept the explicitly recorded validation exceptions: one human-only task and full-suite feedback exceeding 120 seconds. Phase 4 B-36 remains separately deferred; this acceptance does not close it or approve Phase 6 acquisitions.
result: [pending]

## Summary

total: 6
passed: 5
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps

None reported.

## Session Scope and Order

This session resumes the outstanding checks in 05-HUMAN-UAT.md, derived from all 28 execution summaries. It does not repeat or convert the passed automated gate into human approval. User-flow review (tests 1–3) precedes wording and technical fit (tests 4–5), with goal-backward and validation acceptance last (test 6). A failed user-flow check halts advancement until diagnosed and resolved. No automated UI result or paid inference was added by this session.

The roadmap's existing MVP goal was normalized into equivalent user-story syntax without changing its scope, then passed the required format validator. The selected remaining-check scope introduces no cold-start claim. The deferred Phase 4 B-36 clean-room run remains open and requires its own workflow; do not clear volumes/caches or claim it passed through this UAT.

A read-only localhost:8088/chats probe returned connection refused when this session began. Test 1 uses the retained screenshot and needs no running server. Restore the documented existing stack before tests 2–4; no human result is inferred from this environment condition. Do not repeat successful paid Phase 5 suites. Any new user-driven questions remain distinct from the retained automated spend ledger.

No commits/staging, requirement-checkbox changes or Phase 6 acquisition approval. Synchronize actual user results to 05-HUMAN-UAT.md; only genuine final acceptance may update verification status, while retaining B-36 and validation limitations.

Delegated review: user requested "you can use the image yourself". Test 1 passed by assistant visual inspection of the retained screenshot; remaining judgments and final acceptance stay pending.

User delegated browser/screen inspection after confirming test 3 and requested Phase 6 execution afterward. Remaining checks may be inspected by the assistant; neither final subjective acceptance nor the separate Phase 6 package/model admission checkpoint is inferred from this delegation.

Delegated browser review completed using the project CDP harness and installed Chrome after non-destructively starting this checkout's stopped MySQL/ES/Redis/MinIO containers. All eight running devrag services became healthy; volumes retained. Five translated screens were inspected, including a scripted refusal at the local provider boundary. Exact test fixtures were cleaned through AccountRegistry. No paid suite was replayed. The current runtime BGE hash/resource checks pass. Final user sign-off (test 6) is still pending; the explicit request to execute Phase 6 is retained independently.
