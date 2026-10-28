---
phase: 06-deep-parsing-and-chunking-breadth
plan: "06"
subsystem: structured-tables
requirements-completed: []
---

# Plan 06-06: Inspect reconstructed PDF tables and crops

Members can inspect exact structured PDF cells beside their actual authenticated source crops. The pinned TSR model uses an explicit seven-class tensor adapter (1x3x640x640 → 1x11x8400); its extra grid-cell channel is retained. Model row/column anchors combine with agreeing visible raster rulings to recover the merged header and empty cell. Distinct model rows cannot collapse onto partial rules. No fixture, model or score/NMS/quality threshold changed. The original annotated two-page source was frozen before inference; both pages retain exact planted numbers, spans, captions and canonical crop geometry.

Typed bounded Table/Cell values validate complete nonoverlapping spans, text and crop associations. HTML is escaped. Native character rectangles associate actual text with cells; punctuation grouping preserves “Table 1.” and OCR counts intervening white columns correctly with the unchanged segmentation threshold. An empty final cell retains its structural position while passage text starts the next caption on its own line. Native table crops count toward per-item and aggregate budgets; malformed remote page/dimension/SHA associations refuse. Standalone image TSR requires one actual detected table.

The pipeline persists crops through plan05 generation/tenant/document ownership and substitutes opaque IDs before General chunking. Table metadata survives index, chunk, retrieval and saved-reference DTOs; raw bytes, storage keys, crop digests and generated HTML stay out of public table DTOs. Text edits discard stale table metadata. Read-time source visibility still controls references. React renders semantic spans and text nodes, then pairs tables with fresh current-document authenticated crop descriptors. Workspace/source URL cleanup and retry behavior remain covered.

Verification: final rebuilt native03/04/05/06 plus Office/table Chrome23passed; full Python unit2438passed/8existing skips; full frontend2154passed106files and final focused29passed; affected real services140passed; final real authorization matrix58passed; response/log leaks6passed. Production build, generated OpenAPI/types, CI7/7, security/async lint, remote native-import boundary and unchanged exact admission pass. Actual Chrome screenshot was inspected by the assistant. No paid request or new package/model acquisition occurred.

The offline five-repeat guard used the final native image with network disabled,2CPU/3GiB, read-only root/model/fixture mounts, nonroot, dropped capabilities and bounded tmpfs/pids. All quality checks and deterministic crops passed: p95/page2.4681s, peak562.824MiB, cold model load0.8402s, no OOM. The per-page timing is whole two-page parse elapsed/2, with raw repetitions retained. This small fixed source is not production capacity proof;3GiB remains a trial cap pending audio/full-corpus testing. See06-06-TABLE-GUARD.json and06-06-VERIFICATION.json.

## Deviations and review

Supplemental glue was declared in06-06-PROGRESS.md before implementation: runtime/capability protocol, typed table codec, crop association, nonindexed table features, explicit chunk/retrieval/reference DTOs and generated frontend types. Complete actual inventory is06-06-FILES.txt. No schema migration or new public product route was required. Inline review was used; no agents were authorized.

Retained behavioral REDs cover missing table types/spans, chunk/index metadata loss, UI structures, malformed remote crop page/dimensions, native total asset budget, reference redaction, caption punctuation, visible whitespace, row spans/projected headers, partial ruling collapse and empty-cell passage boundaries. The discarded whole-line OCR alternative lost genuine spaces; it is not used. The original fixtures and quality assertions remain unchanged.

R-237 is accepted automatically, not user-reviewed. No REQUIREMENTS.md checkbox changed. Next07 delivers One document chunking and the public static Go catalog. Phase5 final human acceptance and Phase4 B36 remain separate; Phase6 full gate and user UAT remain pending.
