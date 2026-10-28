---
phase: 06-deep-parsing-and-chunking-breadth
plan: "09"
subsystem: structured-records-and-qa
requirements-completed: []
---

# Plan06-09: Ingest structured JSON, CSV and Q&A pairs

JSON and CSV now have strict dedicated parsers and bounded immutable scalar Record/Field metadata. JSON rejects duplicate keys/nonfinite values and enforces depth/value/record/field/size limits before unsafe growth; sorted escaped JSON-pointer paths are deterministic. CSV uses stdlib strict quoted-field decoding with BOM support, header context, exact embedded newline/quote values and physical line evidence. Duplicate headers/mismatched rows refuse. Formula-looking values stay inert strings. Original CSV/JSON/XLSX/TXT fixtures and annotations were frozen before implementation and SHA checks verify them.

QA is a real chunker with its own config: exactly one validated question/answer per chunk, normalized question_tks and full original parsed-record text, including inert extra fields. Question/answer aliases must be unique and share a record parent; empty/missing/ambiguous pairs refuse with fixed terminal qa_invalid. Explicit TXT Question:/Answer: pairs can span paragraphs. Oversize pairs refuse without splitting; actual model context is checked before encode. Unsupported source formats refuse before reading/inference. There is no naive fallback.

XLSX uses a QA-only structured row path with existing ZIP/XML guards, read-only cached values, record/cell bounds and ISO date/time scalar conversion. Generic XLSX's existing header/grouping behavior remains intact. Source geometry and line evidence retain defaults. Build rows add question_tks only when present. The existing question_tks^20 retrieval query remains unchanged; actual Elasticsearch field-only search and full product retrieval find the paired planted answer.

The existing dialog saves Q&A, explains accepted formats/header/text-pair shape and keeps each pair atomic. Python/frontend/static Go catalog availability agree. Fixed EN/ZH failure/helper copy is wired. Actual Chrome uploads CSV and JSON, retrieves the exact52metres multiline quoted answer, and keeps the9100kilograms answer in its own chunk. Source values render as text; no formula/code/resource is executed. Screenshot review is assistant verification, not human UAT approval. Python implements the approved QA mirror scope; Go chunker runtime remains deferred.

Verification: full root2572passed/8existing skips plus final23focused (including four checks added after the full run), frontend2162passed107files and Go internal allpass. Final new worker/browser6passed; native/parser/One/Manual/QA and browser regressions34passed; affected services104passed; routes/OpenAPI70passed; response/log leaks6passed. CI7/7/security/generated/admission pass. Four source formats and invalid-pair refusal traverse real services/provider wire/index. No new dependency/model or paid request. Current images use the already verified matching-manifest runtime and unchanged native vendor cache. See06-09-VERIFICATION.json and complete06-09-FILES.txt.

## Deviations and review

Shared glue was assigned in06-09-PROGRESS before edits: record types, opt-in XLSX rows, pipeline format/context guards, question index metadata, typed failure vocabulary, method config/availability, catalog parity and existing form controls. Normalization golden was corrected against the existing stdlib tokenizer before implementation; it does not stem lighthouse. Fixture-builder dict shape was corrected before freezing source hashes. Date metadata had a meaningful failure and now converts explicitly to ISO text.

Availability-sensitive legacy tests used qa as a deliberately unbuilt method. They now use an explicit unknown unbuilt-fixture sentinel, keeping terminal-code, no-side-effect, failure-line and refusal assertions. Existing disabled-radio tests select a genuinely disabled option rather than assuming index1 is unavailable. A full frontend regression exposed a chat test waiting for URL navigation before React committed its draft; its existing bounded wait now requires URL and draft DOM together, with all assertions retained. No chat production code, retry, skip or paid test changed. These test helpers are included in the actual file inventory.

R-240 is accepted automatically, not user-reviewed. REQUIREMENTS.md remains untouched. Next10 delivers safe EPUB/spine-order Book chunking. Phase5 final human acceptance, Phase4 B36 and full Phase6 gate/user UAT remain separate/pending.
