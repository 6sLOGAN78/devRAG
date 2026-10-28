---
phase: 06-deep-parsing-and-chunking-breadth
plan: "12"
subsystem: legal-sections-chinese-tokenization
requirements-completed: []
---

# Plan06-12: Read legal structure and normalize Chinese text

Laws is a distinct typed-config chunker with chapter/section/article/item ancestry, bounded article chunks and original source characters. Multiline PDF blocks retain their page boxes; one source task preserves article ancestry across selected ranges. Quoted article names and structural code blocks do not become legal headings. The shared section emitter accepts a domain-specific classifier, retaining Paper behavior. The saved dialog, Python factory and Go catalog agree; size applies within articles and ignored delimiter/overlap controls are explained in English and Chinese.

Exactly approved Jieba0.42.1 and OpenCC0.1.7 were inspected and acquired. The whole-app dry run adds only these two; existing package versions are unchanged. The new matching-manifest runtime installs hash-checked local wheels without network/dependency resolution. Approved dictionaries are package-local and hash inventoried; Jieba mutable marshal cache and optional Paddle installation are never used. Normalized Chinese dictionary tokens retain existing unigram/bigram recall and English golden scores. Original source spans survive full-width/combining normalization and link removal; indexed offsets change atomically with edits, and English replacement clears stale Chinese offsets. Conversion work is bounded to128-character runs; any length-changing conversion uses a conservative containing source span. Existing documents need reparsing to gain these new indexed tokens/offsets.

Verification: root2632passed/8existing skips;66 Laws/tokenizer/query/fusion;frontend2165passed107files,focused64;Go allpass. Real Laws index plus Paper/chunk-edit regression51pass; actual Chrome1pass checks both exact questions reached the loopback provider and returned identical traditional source passage. Native/parser/browser regressions40pass;services85pass;routes/leaks172pass;CI7/security/generated/OpenAPI/admission pass. App/worker/native rebuilt and healthy before E2E; offline image tokenization passes with native NumPy absent from app. Screenshot inspected. Evidence hashes and runtime identities are in06-12-VERIFICATION.json; acquisition in06-12-ACQUISITION.json.

Review: inline self-review. RED tests caught missing implementation/parity/offsets, scientific-heading leakage into Laws, missing model-context guard, split PDF scheduling, multiline article loss and stale edited offsets. All fixed in product paths. Initial UI availability snapshots updated for newly available Laws. Screenshot review strengthened browser evidence with exact raw query/provider assertions and fresh-result waits; an intermediate DOM-serialization wait error was a fixture error and is not counted as product evidence. No skips/fallbacks/relaxed assertions added. Full file inventory is06-12-FILES.txt.

R243 accepted automatically, not user-reviewed. No new model or paid call. REQUIREMENTS.md untouched; Phase5 final human acceptance, Phase4B36 and fullPhase6gate/UAT remain pending. Continue13 Presentation.
