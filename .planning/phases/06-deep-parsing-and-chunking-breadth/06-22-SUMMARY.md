---
phase: 06-deep-parsing-and-chunking-breadth
plan: "22"
subsystem: controlled-tagging-and-generated-metadata
requirements-completed: []
---

# Plan 06-22: Apply controlled tags and auto metadata

A dataset manager can enable an allowed tag set and a declared metadata schema, select a registered chat model for each, and parse new documents. The real worker applies bounded model calls with strict typed output checks. Only allowed labels/schema keys enter the index or document metadata; original text and geometry remain intact. Document and flattened endpoints expose generated values with human-first precedence, and document detail reports field provenance. Tag inventory shows generated origin. Text edits clear stale generated tag associations.

Changed paths are listed in `06-22-FILES.txt`. The original fictional source and frozen annotation are `test/fixtures/phase6/controlled-enrichment-original.txt` and `controlled-enrichment-original-annotation.json`; the real provider is a local recorded HTTP fixture only. Actual Chrome screenshots of the generated value/provenance and both allowed labels were inspected. Earlier screenshot framing and a transient regression run during container recreation were corrected and retained as logs; the final outcomes are in `06-22-VERIFICATION.json` and the findings in `06-22-REVIEW.md`.

Verification: focused unit4; full marked unit2613 passed, eight existing skips; frontend2193 passed across113 files; real MySQL/MinIO/Elasticsearch/local-provider integration9; affected stable integration30; rebuilt Chrome4; TypeScript and production build; CI7/7; records5. App and worker matched the final rebuilt image, native image healthy; all full compose services healthy. No new package/model selection, external paid call or ASR replay. Following a host restart that removed prior Docker images, frozen-lock app and hash-locked native images were rebuilt; no package version was changed. R253 accepted automatically, not user reviewed. REQUIREMENTS.md is unchanged.

Next: 06-23 dataset-wide enrichment jobs. Phase5 final human acceptance, Phase4 B36 and the Phase6 final gate/UAT remain open.
