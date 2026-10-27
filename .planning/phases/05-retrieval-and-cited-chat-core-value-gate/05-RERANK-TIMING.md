# Phase 5 real CPU rerank timing (R-219)

Completed 2026-10-27 from eleven recovered rows and one freshly measured recovery row through the production TEIRerank driver, batches of 32, five repetitions per row (60 raw samples total).
The input is repository documentation cut with count_tokens to the stated cl100k token lengths; TEI uses its own tokenizer and truncates at its model limit.

| Pairs | Chunk tokens | p50 seconds | p95 seconds | Pairs/second |
|---|---|---|---|---|
| 16 | 128 | 1.4940 | 1.5965 | 10.71 |
| 32 | 128 | 3.3682 | 3.4919 | 9.50 |
| 64 | 128 | 7.5608 | 7.8129 | 8.46 |
| 128 | 128 | 16.1654 | 17.2023 | 7.92 |
| 256 | 128 | 35.8667 | 37.3656 | 7.14 |
| 1024 | 128 | 129.4687 | 144.2845 | 7.91 |
| 16 | 512 | 6.1942 | 6.2308 | 2.58 |
| 32 | 512 | 11.7907 | 12.3098 | 2.71 |
| 64 | 512 | 22.0052 | 23.6635 | 2.91 |
| 128 | 512 | 43.2977 | 44.7238 | 2.96 |
| 256 | 512 | 86.2379 | 88.7358 | 2.97 |
| 1024 | 512 | 447.6617 | 455.8773 | 2.29 |

Chosen rerank cap at p95 <= 10 s for 512-token chunks: **16**.
Peak sampled container memory: **2267.14 MiB** (docker stats working-set proxy for RSS, sampled throughout the run).
Memory limit with 25% headroom rounded up to 256 MiB: **3072m**.
Restart-to-health with weights already cached: **9.954 seconds**.
Image uncompressed size: **937659489 bytes**.
Model volume: `devrag-stack_tei_data                       1         3.446GB`.
Backend startup log: `2026-10-27T09:39:31.500293Z  INFO text_embeddings_backend: backends/src/lib.rs:468: Model ONNX weights downloaded in 297.311941ms`.
The retrieval pool remains top_k = 1024; only the cross-encoder window is capped.

## Provenance and host load

The first eleven rows are preserved byte-for-byte in `05-RERANK-BGE-RECOVERED-11.samples.json` (SHA-256 b9e0c3d01b3786a411f77a152f063ad030338db69725feb3e79e9e783143f9c9). The final 1024x512 row has five fresh, atomically checkpointed repetitions in `05-RERANK-BGE-RECOVERY.samples.json`. The merged `.samples.json` names both sources and records the cached restart/image/volume/backend evidence. No missing sample was estimated.

The recovery row ran on the approved BGE revision `2cfc18c9415c912f9d8155881c133215df768a70`, AVX2, 1024 internal batch tokens and physical performance cores 0,2,4,6. Host tests were pinned to disjoint efficiency cores 8–15, while the app/worker, a short cached image build and ordinary E2E also ran on the shared host. CPU affinity does not isolate shared memory or other services. Earlier rows likewise included test workloads as documented in the gate log; these are shared-host observations.

The eleven-row run sampled 2249.728 MiB, the final-row recovery sampled 610.300 MiB, and the separate approved startup/guard sampled 2267.136 MiB. Memory sizing uses their maximum, including the startup guard: 2267.136 x 1.25 rounded up to 256 MiB gives 3072m (3 GiB). The dev compose limit is 3g; production has no dev-only memory cap. The cached restart value above was freshly measured after the final row; it is not a first-download time.

The user explicitly approved a ten-second BGE ceiling on 2026-10-27. N=16 at 512 tokens passes; N=32 exceeds it. The original model's quality assertions are unchanged. Historical BGE guards and rejected MiniLM/INT8/UINT8 comparisons retain their explicit filenames and package-audit notes; no rejected model is described as the configured passing model.

Active ONNX artifact verification (2026-10-27): `sha256sum` of the pinned model-cache snapshot returned `15b9a8c3da82eddf263df571281166e00e9308fe19d077084b642ebfcaf06d2b`, matching the approved original BGE weight digest in 05-PACKAGES.md.
