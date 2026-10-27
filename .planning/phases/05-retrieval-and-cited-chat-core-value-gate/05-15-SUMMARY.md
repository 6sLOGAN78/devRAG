---
phase: 05-retrieval-and-cited-chat-core-value-gate
plan: 15
subsystem: retrieval
tags: [tei, rerank, timing, compose]
requirements-completed: []
completed: 2026-10-27
---

# Phase 5 Plan 15: Measured local cross-encoder

The approved original BAAI/bge-reranker-base runs in the pinned TEI cpu-1.9.4 container, with a retained model volume, loopback port 6381 and the internal `tei` alias. Stack scripts include the tei-cpu profile and download-aware readiness/disk checks. AVX2 and host-specific physical-core affinity are recorded in the package and timing evidence.

All twelve timing rows have five raw repetitions each. Eleven recovered rows and the fresh 1024-pair/512-token row are identified separately in [05-RERANK-TIMING.md](05-RERANK-TIMING.md) and its JSON samples. No sample was estimated. At 512 tokens, N=16 has p50 6.1942 s / p95 6.2308 s; N=32 has p95 12.3098 s. Under the user's approved ten-second ceiling, the settings, template, environment example and running app use **16 rerank candidates**. The retrieval pool remains 1024.

Maximum observed matrix/startup memory was 2267.136 MiB. Adding 25% and rounding up to 256 MiB gives **3072m**, expressed as 3g in dev compose. Cached restart-to-health was 9.954 s; uncompressed image size was 937659489 bytes and the model volume was 3.446 GB. The active original ONNX SHA-256 matches the approved audit. These are shared-host measurements, with mixed-run provenance and concurrent workload disclosed; restart timing does not claim a first-download measurement.

Validation: focused settings/probe/environment/compose/records checks passed (155 tests). The final full unit tier passed 2411 tests with six existing skips; the final integration tier passed 905 tests, including all eight real-TEI checks for quality, batching, truncation and changed ranking. The recorded 17-case retrieval API run includes keyless/default-address real TEI and a container-log request assertion. Compose validation, project ownership preflight, CI 7/7 and security/async lint pass. The final complete E2E gate is tracked separately under plan 28.

R-218/R-219 and the closed R-52 record the outcome; B-37 is resolved. Rejected replacement models and the historical five-second results remain explicitly identified. No requirements were ticked, source staged or committed. Phase 4 B-36 was not run or claimed.

## Self-Check: PASSED
