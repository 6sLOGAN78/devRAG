---
phase: 06-deep-parsing-and-chunking-breadth
plan: "11"
subsystem: paper-sections
requirements-completed: []
---

# Plan06-11: Read academic papers by section

Paper is a distinct typed-config chunker. It recognizes explicit headings and whole-line scientific labels (including Chinese and numbered/subnumbered headings), preserves ancestry and source evidence, and splits long sections within the token budget. Prose mentioning Methods or References stays prose; code/table/list blocks cannot create headings. Markdown ATX/setext syntax becomes clean section labels. Existing typed tables, images, source lines and page boxes survive, and actual model context is checked before encoding.

PDF Paper parsing schedules one bounded source task so sections can continue across the former task page boundary. It reuses existing selected-page range merging and bounded text accumulation, control checks and native service path. Original Markdown and two-page PDF fixtures were frozen before implementation. Real worker/index checks find exactly Abstract, Introduction, Methods, Measurements and References, with Methods positions on both pages. The existing dialog saves Paper, retains it on reopening and explains section-based controls. Python, frontend and static Go catalog agree on availability.

Verification: final root2621passed/8existing skips;16focused;frontend2164passed107files;Go internal allpass. Real nativePDF/Markdown worker2pass, actual Chrome1pass with inspected Methods73 citation, parser/native/browser regressions39pass, services84pass, routes/leaks172pass, CI7/security/generated/OpenAPI/admission pass. Actual app/worker/native rebuilt and healthy before E2E. No new dependencies/models or paid calls. Evidence hashes and image identities are in06-11-VERIFICATION.json.

Review: inline self-review. Hardening RED4fail12pass caught structural-block false headings and setext label syntax; final16focused plus full suite pass. PDF scheduling regression first failed and then passed with whole-source task selection. Legacy disabled-Paper tests now use still-unbuilt Audio with original refusal assertions. A full frontend run exposed mobile assistant-dialog readiness: the input existed before its mount focus effect. Its existing bounded wait now waits for focused input before retaining all one-dialog/closed-rail/focus-return assertions. This is test-only supplemental glue; no chat production change, retry, skip or timeout relaxation. See06-11-PROGRESS.md and complete file inventory.

R242 is accepted automatically, not user-reviewed. REQUIREMENTS.md is untouched; Phase5 final human acceptance, Phase4 B36 and full Phase6 gate/UAT remain pending. Continue12 Laws/Chinese normalization with the previously approved exact OpenCC/Jieba packages and source-build inspection.
