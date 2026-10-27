---
status: pending
phase: 05-retrieval-and-cited-chat-core-value-gate
updated: 2026-10-27
---

# Phase 5 human checks

These checks supplement automated evidence. The automated Phase 5 gate passed; final approval and the remaining human checks stay pending. The user delegated screenshot inspection to the assistant; that result is attributed separately below.

1. **PDF citation alignment.** The criterion-5 journey passed. Inspect the retained `screenshots/phase5-core-source.png` and open the source drawer on a real document. Confirm the highlighted rectangle covers the sentence containing the planted lighthouse fact. Automation proves the rectangle lies within the page image; it does not prove word-level alignment. Result: PASS by assistant visual inspection at the user's explicit request ("you can use the image yourself"). The highlight encloses both lines containing "52 meters above Corvane Bay" and matches the passage. This is retained-screenshot evidence, not a new live run or blanket user approval.
2. **Chinese copy.** Review `web/src/locales/areas/zh/{assistant,chat,retrieval,source}.json` in the corresponding screens. Check the sharing, refusal, stopped answer, citation and score descriptions for natural wording and accurate meaning. Result: PASS by delegated assistant copy/browser review of five Chinese UI states; evidence: output/playwright/phase5-review/. The upstream provider was local/test-only; no paid quality result was replaced.
3. **Answer usefulness.** Upload a real document, ask two free-form questions, open the cited passages, and judge whether each answer is supported and useful. The planted numeric-fact tests do not replace that judgment. Result: first real-document answer PASS, confirmed by user ("okk  pass"); second answer PASS, confirmed by user ("pass you can use google chrome or anything control screen and check out you self").
4. **Local reranker footprint.** Compare the approved model/artifact and recorded digest with the active container, measured model volume and timing evidence. Confirm the chosen model's language coverage fits the intended documents. A failed experimental model must not be reported as a passed gate. Technical evidence is complete: all 12 timing rows / 60 repetitions, cap 16, 3 GiB memory, 9.954 s cached restart and 3.446 GB model-cache volume. The active original BGE ONNX digest is `15b9a8c3da82eddf263df571281166e00e9308fe19d077084b642ebfcaf06d2b`, matching the approved artifact. Delegated technical review PASS: rechecked the active hash, healthy container, 3 GiB limit, four-CPU quota, affinity and 3.446 GB cache. The official model card identifies English and Chinese; fitness is limited to that documented language scope. Other intended languages and final acceptance are not inferred.
5. **Phase 4 clean room.** The separate Phase 4 clean-room item B-36 remains open. This Phase 5 work does not claim it ran or passed. Result: outstanding prior-phase item.

Pending: 1 prior-phase item (B-36); final Phase 5 acceptance remains pending in 05-UAT.md test 6. Passed: 4 checks (delegated alignment, Chinese copy and footprint inspection; user-confirmed two-answer usefulness). No approval is inferred for the remaining items.
