---
phase: 06-deep-parsing-and-chunking-breadth
plan: "23"
subsystem: dataset-enrichment-jobs
requirements-completed: []
---

# Plan 06-23: Run dataset-wide enrichment jobs safely

A dataset manager can start and cancel a bounded enrichment refresh. Visible members can list jobs and see real child counts. The worker refreshes generated tags and metadata on existing indexed chunks without reparsing, reembedding, or inventing a document for the job sentinel. The browser shows progress and completion in the dataset workspace. The frozen source/configuration digest, real task rows, Valkey Stream messages, current-source checks and normal worker lease/retry paths make duplicate delivery and interrupted publication recoverable.

The exact changed paths are in `06-23-FILES.txt`. The fictional source and its prior annotation are `test/fixtures/phase6/controlled-enrichment-original.txt` and `controlled-enrichment-original-annotation.json`. A local deterministic HTTP model supplied the planted lighthouse label and metadata value. The actual Chrome job screenshot was inspected. The review, including two known partial-publication boundaries, is in `06-23-REVIEW.md`.

Verification: full marked Python unit 2616 passed with eight existing skips; real MySQL/Elasticsearch/local-provider integration five; rebuilt browser completion/cancellation two, including duplicate delivery with two workers; route isolation 24; live response leak sweep six; frontend 2195 across 114 files; TypeScript/build and Go internal; all seven CI gates. The final app and worker use the same rebuilt image and the full compose stack is healthy. No new package/model selection, external paid call or ASR replay. R-254 is accepted automatically, not user reviewed. `REQUIREMENTS.md` is unchanged.

Next: Plan 06-24 RAPTOR summaries and source citations. Phase 5 final human acceptance, Phase 4 B36 and Phase 6 final gate/UAT remain open.
