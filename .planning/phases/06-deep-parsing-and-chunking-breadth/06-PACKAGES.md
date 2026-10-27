---
phase: 06-deep-parsing-and-chunking-breadth
status: awaiting_human_acquisition_approval
created: 2026-10-27
---

# Phase 6 package, model and live-budget review packet

This is the concrete audit for checkpoint06-01. Nothing below is an inferred user approval. No install/native weight download/provider inference occurred while preparing it. Existing Phase5 npm/TEI/BGE approval is retained for that exact scope only. Candidate metadata and hashes are in06-SOURCE-EVIDENCE.json;40-package wheel-only resolution in06-CANDIDATE-WHEELS.txt, plus separate source-only Jieba. A lock resolution proves selectable metadata, not native runtime compatibility or supply-chain clearance.

## Requested acquisition

| Exact candidate | Registry license declaration | Selected release date | Declared source repository | Scan / acceptance |
|---|---|---|---|---|
| `onnxruntime==1.23.2` | MIT License | 2025-10-22 | [onnxruntime](https://onnxruntime.ai) | OK; [ASSUMED] acceptance |
| `numpy==2.2.6` | Copyright (c) 2005-2024, NumPy Developers. All rights reserved. Redistribution and use in  | 2025-05-17 | [numpy](https://numpy.org/doc/) | OK; [ASSUMED] acceptance |
| `opencv-python-headless==4.12.0.88` | Apache 2.0 | 2025-07-07 | [opencv-python-headless](https://github.com/opencv/opencv-python) | OK; [ASSUMED] acceptance |
| `pyclipper==1.4.0` | MIT | 2025-12-01 | [pyclipper](https://github.com/fonttools/pyclipper) | OK; [ASSUMED] acceptance |
| `shapely==2.1.2` | BSD 3-Clause | 2025-09-24 | [shapely](https://shapely.readthedocs.io/) | OK; [ASSUMED] acceptance |
| `jieba==0.42.1` | MIT | not retain | [jieba](https://github.com/fxsjy/jieba) | OK; [ASSUMED] acceptance |
| `opencc-python-reimplemented==0.1.7` | Apache License | 2023-02-11 | [opencc-python-reimplemented](https://github.com/yichen0831/opencc-python) | OK; [ASSUMED] acceptance |
| `scikit-learn==1.7.2` | BSD-3-Clause | 2025-09-09 | [scikit-learn](https://pypi.org/project/scikit-learn/#files) | OK; [ASSUMED] acceptance |
| `umap-learn==0.5.9.post2` | BSD | 2025-07-03 | [umap-learn](http://github.com/lmcinnes/umap) | OK; [ASSUMED] acceptance |
| `faster-whisper==1.2.1` | MIT | 2025-10-31 | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | OK; [ASSUMED] acceptance |

Registry existence and clean name scans are not user acceptance. The candidate set remains [ASSUMED] for planning and is gated before install. Direct scan:10/10 OK. Complete wheel resolution:37 OK,3 SUS,0 SLOP. Read-only slopcheck0.6.1 scan ran against scratch requirements files; its actual install subcommand was deliberately not used because it installs packages. No --fix/--force/allowlist change was used.

- `httpx2==2.16.0`: SUS name-similarity signal. Source identity context is recorded below; no package was installed or allowlisted.
- `numba==0.68.0`: SUS name-similarity signal. Source identity context is recorded below; no package was installed or allowlisted.
- `sympy==1.14.0`: SUS name-similarity signal. Source identity context is recorded below; no package was installed or allowlisted.

Source identity checks: [Hugging Face's v2 migration documentation](https://huggingface.co/docs/huggingface_hub/concepts/migration_v2) explicitly documents httpx2 as its HTTP transport; [Numba's official install guide](https://numba.readthedocs.io/en/stable/user/installing.html) and [SymPy's install guide](https://docs.sympy.org/latest/guides/getting_started/install.html) identify their package names. These explain why a similarity heuristic alone is insufficient; the original SUS reports remain preserved. Their exact wheel hashes and metadata remain subject to the checkpoint, with no claim that a source link alone proves a particular wheel safe.

OpenCV4.12 requires NumPy<2.3, so NumPy2.2.6 is pinned. Source-only Jieba requires review of its source/setup before any build. The resolution selected CTranslate2/PyAV for local ASR and Numba/PyNNDescent/SciPy/llvmlite for clustering; see every pinned transitive license/version/source/date in06-TRANSITIVE-EVIDENCE.json. CPU wheels target Python3.13/Linux x86-64. No system package, new npm package, GPU runtime, new orchestration framework or cloud parser SDK is implicitly approved. A different SDK/image/model/version triggers a supplemental concrete audit before acquisition. The native image is a local DeepDoc build using the project's existing Python base; its final digest/size is measured after the accepted build, not invented here.

## Exact model candidates

DeepDoc: `InfiniFlow/deepdoc`, revision `9c7aa2c730d7a242d7f04cf6109a6a239aefc717`. Required unique ONNX/dictionary files total **103568065 bytes** (~98.77MiB); aliases layout.paper/laws share the observed layout hash and need no duplicated bytes. Exact per-file size/LFS SHA and dictionary SHA are in06-SOURCE-EVIDENCE.json. The26,249-byte text dictionary was read for SHA verification; no ONNX weights were downloaded. The [model card](https://huggingface.co/InfiniFlow/deepdoc) declares Apache-2.0; artifact-specific internal provenance is not yet inspected. Preserve the historical upstream metadata discrepancy as an audit item; do not present it as a legal conclusion about these current bytes. Acquisition approval permits the bounded artifact inspection/quality probes; any actual conflicting provenance or failed fixed quality result is recorded before the model is accepted as the final runtime.

ASR: `Systran/faster-whisper-tiny`, revision `d90ca5fe260221311c53c58e660288d3deb8d356`, metadata bundle **78207087 bytes** (~74.58MiB), [declared MIT model card](https://huggingface.co/Systran/faster-whisper-tiny). Multilingual tiny is selected for CPU feasibility, not an unmeasured quality claim. No weight was downloaded. Local-only loading, exact snapshot/hash verification, VAD disabled unless separately provisioned and bounded WAV/MP3 fixtures are mandatory. No automatic model upgrade.

These model-byte totals exclude package wheels, expanded image layers, temporary build/cache storage and base images. Peak RSS, startup, OCR/table/audio accuracy and CPU throughput are **unmeasured** for this phase. Proposed trial service guards:3GiB dev memory,2CPU quota, one concurrent native parse, bounded100MiB input/40MP page/32MiB output,300s parse/60s per-page deadline. Fixed quality probes and five-repeat CPU/RSS guard precede capacity selection; actual memory +25% rounded to256MiB determines the eventual measured limit. Stop with retained evidence on a failed guard; do not silently enlarge it.

## Proposed new live spend (acceptance pending)

| Kind | Maximum per selected Phase6 live attempt | Includes |
|---|---:|---|
| Chat-class |20| Provider-save probes, keywords/questions/tagging/metadata/resume/RAPTOR and supported-answer journey |
| Vision |6| Save probes and figure/picture descriptions |
| Cloud OCR |6| Bounded provider-save probes and hosted OCR/parser jobs; overlapping classifications are reported separately |
| Local ASR |3| Save probe, WAV and MP3 fixture |
| External parser submits |8| One fixed one-page submit per explicitly configured backend, with bounded polling under the same job |
| Query embeddings |12| Retrieval/answer queries, including bounded fallback |
| Embedded source + summary chunks |200| Ingestion and RAPTOR summary outputs; actual embedding request counts also logged |

Counters increment before calls and count cancellations/retries. No broad paid suite replay. The final ledger also reports disjoint/cross-class counts so an OCR submit appearing in two classifications is not added twice as a supposed total bill. Earlier Phase5 successful14 tests and failed-attempt spend remain retained separately and are not rerun by default. Native OCR fixtures are local calls; no external billing is implied by the ASR/local-native caps.

Optional cloud backends require their actual endpoint/version/credentials: existing OpenRouter key does not stand in for PaddleOCR/Mistral/Tencent/SoMark access. Docling/MinerU/OpenDataLoader service profiles/URLs likewise need the actual configured service. No key value should be entered in this audit or printed. Implementation can have deterministic transport fixtures, but no absent provider is marked as a real gate pass.

## Approval choices

The pending06-APPROVAL.json deliberately contains no human response. Accept the exact candidate snapshot for acquisition, bounded native probes and the listed live caps, or name rejected packages/models/caps. Approval is recorded verbatim and bound to current artifact/lock digests. Rejection leaves dependent plans blocked until a revised equivalent passes the same corpus. Approval of acquisition does not assert that later quality/footprint tests or Phase5 human UAT passed.
