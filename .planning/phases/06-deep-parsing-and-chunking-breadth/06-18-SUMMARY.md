---
phase: 06-deep-parsing-and-chunking-breadth
plan: "18"
subsystem: resume-entities
requirements-completed: []
---

# Plan06-18: Read structured résumé sections

A member saves Resume and inspects labelled name/contact/work history/education/skills with original source support. A deterministic explicit-heading path makes no model request, even when opt-in is enabled. Missing/unknown values stay absent; invalid claimed contacts fail. A separate explicit unstructured path uses the selected tenant chat model or workspace default, one physical request per input, fixed untrusted-source instructions and strict JSON source-index/Unicode-offset fields. The product derives every value from its original span, never accepts invented response values. Sources128/16Kchars/6000tokens, fields64 and response64Kchars bound extraction; full prompt plus2048output/64overhead must fit actual configured model context. Automatic retries and JSON repair are disabled.

Existing named executor/limiter, cancellation fences, sealed tenant model resolution and usage accounting are reused. Both caller and inference thread release database connections across model wait. No source/response logging. Whole-PDF scheduling/selected-range aggregation reuses One/Paper/Laws behavior, preventing one model call per task window on a long/disjoint PDF. This necessary ingestion_service glue was added after review RED2; no new API route or persistence schema. Typed section paths, original boxes/line support and exact source values travel through existing index/inspector/source mappings.

Existing form adds explicit inference opt-in/model selection, clear disclosure and EN/draftZH copy. Chunk size remains effective; delimiter/overlap are disabled. Document config/detail fields and generated OpenAPI, frontend service mappers/save/reopen, Python/Go/frontend availability and catalog agree. Test UI server now reflects implemented methods and preserves these settings; unbuilt fixtures use Tag. No automatic parse on save.

Original fictional résumé and annotation frozen before implementation; initial8 behavioral RED, caller-release RED1, unknown-contact RED1 and page-scheduling RED2 retained. Current reviewed108 includes all14Resume cases and affected prior structure/model/config behavior; markedunit2576/8existing skips precedes4final review cases; unmarked51pass. Fullweb2180/110files, focused69, Go, actual rebuiltChrome1 and sequential services54, CI7/security/generated/OpenAPI/admission pass. Real SQL/MinIO/ES plus HTTP test provider prove structured0calls, explicit1call, schema/contact refusal1call/no repair, missing model0calls, smallcontext0calls,429exactly1request/no retry; all values/ownership/source evidence asserted. Current app/worker SHA matches workspace. Screenshot inspected: Resume / Work History and original52metres/73units visible. No external paid inference; real résumé paid evaluation belongs30.

Review corrected caller connection release, unknown placeholders and whole-document scheduling. An integration run overlapped recreation and failed connection setup; original1failed/28passed/7errors retained, then final sequential stable-health54passed. Root npx selected an unrelated TypeScript command and failed; project-local compiler/build pass and manifests unchanged. Existing approved unused/unshared build-cache cleanup reclaimed830.3MB then6.429GB, exact fresh IDs including28reclaimable reusable execution snapshots; image inventory identical, no image/container/volume/network/project-file deletion. No package/model acquired. All3previousASR calls remain exhausted and were not replayed.

Inline review only. R249 accepted automatically, not user-reviewed. No REQUIREMENTS checkbox changes. Phase5 final human acceptance,Phase4B36/fullPhase6gate/UAT remain pending. Continue19 Tag/PageRank producer.
