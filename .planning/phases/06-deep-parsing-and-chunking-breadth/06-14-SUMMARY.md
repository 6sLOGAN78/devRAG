---
phase: 06-deep-parsing-and-chunking-breadth
plan: "14"
subsystem: table-rows
requirements-completed: []
---

# Plan06-14: Retrieve table rows with their headers

Table is a distinct typed-config chunker: one logical data row per chunk, repeated original caption and column-header ancestry, empty cells retained, merged spans expanded with exact values. Chunk size is the intact row budget; overflow refuses instead of splitting values. Actual embedding context is also guarded. Non-table prose around typed PDF tables is ignored; an entirely unstructured source refuses. Source boxes, owned table crops and image IDs remain real. CSV physical lines (including quoted multiline values) and XLSX row numbers are preserved without invented coordinates.

CSV and XLSX have explicit Table-only modes; General/QA continue through existing behavior. CSV uses the uploaded document title passed by the pipeline, rather than spool basename. XLSX streams actual cells while ignoring untrusted dimensions before materializing merged ranges; global cell cap and bounded Table dimensions apply. Python/Go/frontend availability agree, saved Table selection persists, and English/Chinese guidance explains whole-row budget and ignored delimiter/overlap settings. Existing safe structured source rendering shows only the matching row and headers.

Verification: finalroot2647passed/8existing skips;focus40/slice7;frontend2170passed109files;Go allpass. Real CSV/XLSX/nativePDF3pass, original CSV title2pass; nativePDF produces6rows with owned crops and actual boxes. Chrome1pass on latest app/worker checks saved choice and Lighthouse height52 distinct from Orchard harvest52; screenshot inspected. Earlier parser/native/browser47pass;services85;routes/leaks172;CI7/security/generated/OpenAPI/admission pass. Exact log hashes/runtime identities are in06-14-VERIFICATION.json, full files06-14-FILES.txt. No new package/model/paid call.

Review: inline self-review. RED caught missing Table/modes and surrounding PDF prose rejection. The native fixture first used a local legacy setting (no typed TSR), then lacked the normal generation record; it now explicitly selects approved DeepDoc and uses existing begin_run operation-log helper. No production generation guard changed. Browser template initially carried an invalid generated MIME; fixed only test MIME. Self-review found spool-derived CSV title; exact real index RED then product pipeline title fix. Final source/input budget, empty/merged cells, quoted CSV, duplicate headers, oversized rows and model budget are covered. No added skips/fallbacks or requirement checkbox edits.

R245 accepted automatically, not user-reviewed. Phase5 final human acceptance, Phase4B36 and fullPhase6gate/UAT remain pending. Continue15 Picture/vision.
