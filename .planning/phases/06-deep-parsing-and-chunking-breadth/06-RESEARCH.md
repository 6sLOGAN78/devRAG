---
phase: 06-deep-parsing-and-chunking-breadth
researched: 2026-10-27
status: complete_for_planning
mode: auto
---

# Phase 6 research

## Scope and provenance

Plan all 58 roadmap requirements, the four Phase 4 remainders and the explicit RETR-13 producer handoff without reducing breadth. No Phase 6 discuss session exists: choices here are **auto-selected engineering assumptions**, not user-confirmed decisions. Phase 5's automated criterion-5 journey passed; its human UAT/approval and Phase 4 B-36 remain open. This research neither closes them nor re-spends their provider budget. `06-REQUIREMENT-SCOPE.json` retains exact source descriptions. No package installed, native ONNX/ASR weight downloaded or paid inference called during research. The 26,249-byte text OCR dictionary was read to hash its manifest entry.

`docs/spec.md`, all `docs/06-document-processing/*.md`, relevant `docs/05-rag-pipeline/{preprocessing,parsing,chunking,indexing,ingestion-pipeline}.md`, `docs/04-api/{dataset,document,workflow}-api.md`, `docs/11-llm/prompt-management.md` and `docs/20-security/file-security.md` are canonical. Source excerpts use local reference commit `6677f14bdff0e80b29ec94378ebd02a9c4ef8d54` at `/home/logan78/desktop x/ragflow`; no upstream checkout or source was modified. Current upstream differs from that snapshot, so do not mix model/runtime contracts blindly.

## Existing system and architectural responsibility map

| Concern | Current seam | Phase 6 responsibility |
|---|---|---|
| Dataset/document permission | `api/db/services/tenant_scope.py`, `knowledgebase_service.py`, `document_service.py` | Authorize every new route before any storage, model or index access; visibility applies within tenant as well as between tenants |
| Parser and chunk contracts | `rag/parsers/types.py`, `rag/chunking/types.py` | Backward-compatible typed extensions for assets, structure and audio; keep existing call sites/tests green |
| Router/factory | `rag/parsers/router.py`, `rag/chunking/factory.py`, `common/ingest_codes.py` | Replace md/csv/json-as-TXT dispatch and NaiveConfig-for-every-method; no fallback to naive for an unbuilt method |
| Worker orchestration | `rag/svr/pipeline.py`, `task_executor.py`, `control.py`, `progress.py` | Keep leased retries, cancellation and named executors; native inference outside the worker when deepdoc is configured; preserve final roll-up locking fix |
| Native processing | New `deepdoc/` Quart service | Only approved CPU inference/decoding, no MySQL/Valkey/MinIO/provider credentials and no arbitrary URLs or host paths |
| Model credentials/usage | `rag/llm`, `api/db/services/llm_service.py` | Add vision, ASR and OCR model types through ProviderSpec/LLMBundle using documented flags8/4/64 respectively (TTS32 stays reserved), seal credentials, bound usage, no new agent framework |
| Search/source rendering | `rag/nlp/search.py`, `retrieval_service.py`, `chat_turn_reference.py` | Store enrichment in current tenant index; resolve RAPTOR to authorized source leaves before retrieval/reference exposure |
| UI | Existing dataset files, chunk-method dialog, parse configuration, chunk inspector and source drawer | Incremental controls/sections using existing theme/components and workspace request fencing |
| Schema | `api/db/models/knowledge.py` plus migrations/exporters | Use existing parser_config, task_type, pagerank and derived-task fields where sufficient; any necessary new relation uses Peewee migration and real MySQL verification; Go remains verify-only |

## Native runtime and model acquisition

Use ONNX Runtime CPU, explicit CPUExecutionProvider and finite input/output checks. Reimplement narrowly against published model tensors; reference preprocessing/postprocessing only with retained notices and fixture parity. Do not import the entire upstream DeepDoc package: its constructors download at runtime and bring unrelated dependencies. The official ORT Python API documents InferenceSession and CPU installation [here](https://onnxruntime.ai/docs/get-started/with-python).

The exact DeepDoc model manifest is pinned in `06-SOURCE-EVIDENCE.json`: repository revision **9c7aa2c730d7a242d7f04cf6109a6a239aefc717**, four unique ONNX files plus `ocr.res`, **103568065 bytes** combined. Layout paper/laws aliases have the same observed SHA as layout.onnx: a provisioner should avoid three copies. The dictionary SHA is `28b2362ad4ab2dc38769aa72feb535e3a9ddb3fd2a7585a05920e6393b1dc7f7`. Each LFS SHA, byte count and immutable source URL belongs in a checked-in manifest. Download into staging with size/hash checks and atomic publish; build/init is the only network acquisition path. Readiness must fail when any required artifact is missing, invalid or incompatible. First parse must never download, install, exec a shell command or fetch Python code.

The [model card](https://huggingface.co/InfiniFlow/deepdoc) declares Apache-2.0. A historical [upstream artifact-metadata report](https://github.com/orgs/infiniflow/discussions/2257) describes differing embedded metadata. The current blobs have **not** been inspected, so this is an unresolved artifact audit, not a claim that current weights have a particular legal status. The checkpoint must explicitly accept or reject the exact candidate after provenance review; a rejected candidate blocks these features until a compatible replacement passes the same fixed quality corpus.

ASR candidate: [Systran/faster-whisper-tiny](https://huggingface.co/Systran/faster-whisper-tiny), revision **d90ca5fe260221311c53c58e660288d3deb8d356**, metadata bundle **78207087 bytes**. Use multilingual tiny, local-only loading and no VAD model auto-fetch. The [official faster-whisper implementation](https://github.com/SYSTRAN/faster-whisper) provides CPU int8 and segment timestamps; MP3/WAV decoding is isolated in DeepDoc. Hardware language/accuracy fit is measured rather than assumed. Higher-capacity models are a new bounded choice, not an implicit download.

Auto-selected trial guards for the approval packet: dev CPU quota two, initial service cap 3 GiB, input 100 MiB, rendered-page pixel budget 40 million, output JSON cap 32 MiB, parse deadline 300 s/document, per-page inference 60 s, concurrency one native document per replica, tmpfs bounded. These are proposed guards, not measured capacity. After approval, fixed OCR/layout/table/audio fixtures run before throughput calibration; report per-page p50/p95, peak working set, cached/cold start, exact image/cache footprint. If OOM, output corruption or >30 s/page p95 appears in the five-repeat guard, preserve evidence and stop for a concrete resource/model decision. Never silently loosen quality assertions or memory caps.

## DeepDoc protocol and coordinate contract

New internal endpoints on port 9390: `GET /health`, multipart `POST /v1/parse`, `/v1/ocr`, `/v1/layout`, `/v1/tsr`, `/v1/document/info`, `/v1/page-image`, and `/v1/asr` when its approved assets are enabled. Use Quart/Hypercorn already present. Define request/response Pydantic schemas and a schema-version field; the source is bytes plus bounded options, never a caller path/URL. Responses contain typed blocks, report counters and bounded asset descriptors/content; binary page-image is a separate response. API key is an operator secret shared only with trusted clients, compared in constant time. Internal errors expose fixed codes, no native traceback, path, source text or provider secret.

Canonical geometry remains **one-based page number, top-left origin in page units**, with `PageBox(page,x0,top,x1,bottom)` and explicit page dimensions. PDF raster zoom is 3; map model pixels back exactly once, after crop/rotation transforms. Preserve all positions across page-range tasks and cross-page tables. Normalized external coordinates are multiplied by page dimensions once; Docling bottom-left coordinates are inverted once. Missing coordinates remain missing, not fabricated full-page highlights. Native text, OCR text and layout regions share this contract. Match native text to layout at intersection/text-box-area >=0.4, use IoU NMS, then stable column-aware reading order; filter header/footer blocks before chunking. TSR emits escaped, structured table HTML with row/column spans and matching crop IDs.

`DEEPDOC_URL` takes precedence over `TENSORRT_DLA_SVR`; only configured operator endpoints can bypass public-address guards, never values embedded in parser_config. If remote native processing is selected, native render/OCR/layout/TSR modules are not imported in the worker or API. Page count, thumbnails and authenticated page previews use the service too. No silent local fallback on service refusal/outage. Extend make/preflight/wait and test-compose profiles explicitly; ordinary parsing remains green with the required profile active. The service has no Docker socket, runs non-root/read-only with bounded tmpfs and dropped capabilities, and production publishes no host port.

## File and chunk breadth

Each feature plan adds a full parser-to-chunk-to-index/inspector slice using its own fixture. Markdown preserves headings, fenced code and tables; JSON preserves bounded paths/records; CSV uses csv.reader quoting and header context; EPUB follows spine order with safe ZIP/XML handling and no remote resources; email uses stdlib MIME decoding without downloading attachments; DOCX/PPTX images resolve archive relationships without path traversal. Images and table crops use the documented tenant/doc object paths, deterministic hashes and SQL-backed ownership records before authenticated downloads. Dedup is limited to the same tenant/document ownership boundary, never a global content oracle. Source deletion/reparse must collect obsolete assets safely.

Build all fourteen methods, exposing each through the existing chunking dialog only after its implementation is reachable: naive, paper, book, laws, presentation, table, qa, resume, picture, manual, email, tag, one, audio. Method-specific configs replace the current unconditional NaiveConfig. Whole-document `one` means exactly one chunk; if provider context cannot hold it, refuse explicitly rather than silently split. QA records question tokens; table repeats title/headers per row; presentation stays within slide boundaries; manual preserves code/table/figure groups; resume returns validated entities with missing values omitted; audio has monotonic timestamps. Chinese normalization adds OpenCC and a dictionary tokenizer while preserving existing full-width folding, URL/email removal and position contracts. Do not alter the Phase 5 citation-rule digest or broaden advanced chat scope.

## Enrichment, metadata, fan-out and RAPTOR

Opt-in counts/defaults are explicit: auto_keywords 0..32, auto_questions 0..16, tag set max128 distinct bounded strings, metadata schema max32 scalar/array fields and max16 KiB validated serialized output; no arbitrary nested code/schema evaluation. Treat document text as untrusted data in fixed prompts. LLMBundle is the only model entry point: tenant-scoped model IDs, generation whitelist, per-stage timeouts/cancellation, exact usage counters, no prompt/answer logging. Set keywords/questions/tag feature fields at index construction and keep manual source text/positions unchanged. Unknown tag labels/metadata keys are refused or omitted by a declared schema rule with fixtures, never accepted as HTML or executable values.

Use existing Knowledgebase.pagerank as the authorized producer for pagerank_fea, plus normalized tag weights. Extend rank-feature consumption with the documented tag cosine formula and 10*tag+pagerank, without changing baseline weights, normalization or Phase 5 golden scores when no features exist. This closes only the explicit RETR-13 producer remainder; unrelated Phase 5 partials stay partial.

New routes are exactly the documented dataset tags/metadata, document metadata/image/artifact, derived-index alteration and built-in pipelines families. Prefix `/api/v1` consistently. The built-in pipeline catalog is the explicit exception to the Python route default: docs/04-api/workflow-api.md assigns its two public static GET routes to Go Gin. Keep those responses static and credential/tenant-free; all tenant-aware routes here remain Python-owned. Static tags/metadata paths must precede dynamic dataset IDs in route matching. All routes enter `conf/routes.yaml`, auth/isolation invokers, cross-tenant matrix, leak sweep and generated frontend schema. Reuse service authorization, not a controller-only check. New JSON in existing schema fields is preferred; required asset/job relations get Peewee migration, generated Go entities and real migrated MySQL tests before use.

Dataset-wide jobs must have an explicit dataset context keyed by tenant/dataset/task_type, not a sentinel passed to Document.get(). Preserve queue locking/reclaim/retry semantics, finite fan-out and idempotent child scheduling; cancellation/deletion stops generation. A built-in pipeline catalog is finite documented data for these methods, not a canvas engine from Phase 7.

RAPTOR is real recursive clustering, summarization and embedding, not concatenated text called a tree. Auto-select seeded UMAP + GMM with bounded cluster counts, small-N deterministic grouping, max3 levels, max64 summaries/run, token/context budgets, explicit parent/leaf IDs and content/model/config-derived generation digest. [The original RAPTOR repository](https://github.com/parthsarthi03/raptor) is the algorithm reference; the local newer RAGFlow watershed implementation is an alternative, not a requirement that overrides our docs. Task cancellation is checked before each paid call and publish. Publish a completed generation atomically; retries do not duplicate summaries. Sources disabled/deleted/reparsed invalidate descendants before they can appear in retrieval. A summary is visible only if every contributing leaf is currently openable; citations resolve to authorized source leaves, never to a fabricated sentinel PDF. Derived deletion/alteration audits and generated-artifact access remain tenant/dataset scoped and bounded.

## External parser contracts

All named backends are planned, no generic dummy adapter is counted as support. Use existing httpx for remote transports and pinned response fixtures captured from each real dialect. Select via validated `layout_recognize`/backend config; operator base URL/credentials stay out of dataset input. No redirect-following, unsafe response ZIP extraction, unbounded poll loop or implicit native fallback.

| Backend | Researched transport | Required evidence |
|---|---|---|
| Docling | docling-serve `/v1/convert/file` or its pinned `/v1/convert/source` dialect; DoclingDocument body/blocks with page provenance | Real selected service parse; goldens for bottom-left coordinates and tables; [upstream](https://github.com/docling-project/docling-serve) |
| MinerU | `/file_parse`, bounded returned content-list/middle JSON or ZIP | Explicit API version, safe archive extraction and normalized 0..1000 bboxes; [upstream](https://github.com/opendatalab/MinerU) |
| PaddleOCR | `/api/v2/ocr/jobs` submit/status in the pinned local reference | Signed-in provider test or operator-local compatible service; preserve job polling/cancel deadline |
| Mistral | multipart/upload or base64 document to `/v1/ocr`; pages markdown and image data | Exact selected OCR model, credential and budget, no `latest` model alias in the final audit; [API](https://docs.mistral.ai/api/endpoint/ocr) |
| TCADP | Tencent LKEAP `ReconstructDocumentSSE`, API v20240522, signed streaming result | Pin action/version/region in adapter contract and recorded fixture from the actual provider; signature adapter using existing crypto/httpx or an audited SDK |
| SoMark | Pinned local reference submit/check/usage dialect | `POST /parse/async`, `POST /parse/async_check`, `/usage` under the approved `/api/v1` base; explicit key/URL, bounded poll and pinned response fixture |
| OpenDataLoader | `/v1/convert/file` hybrid service, with Docling-style nested JSON normalization | Actual service fixture and page bounds; [upstream](https://github.com/opendataloader-project/opendataloader-pdf) |
| Figure parser | Extracted asset + bounded surrounding context through configured vision model | A figure description backed by its real stored asset and current document authorization |

Cloud adapters with absent credentials are recorded as explicit execution prerequisites, not passing tests or production fakes. Deterministic mock transports belong only to tests; the final gate lists real provider/service validations separately. Acquire no external-parser images/SDKs without the package checkpoint audit.

## Package Legitimacy Audit

Registry/metadata candidate audit, checked 2026-10-27. The installed scanner's scan command was used because its install command actually installs packages; no install or --fix mode ran. Read-only slopcheck 0.6.1 scan returned OK for all ten direct names (06-PACKAGE-SCAN.json); no sdist execution was performed. Name checks do not approve compatibility, model use or cost; **all legitimacy dispositions are [ASSUMED] and require a blocking human checkpoint before installation**. Source registries, maintainers, licenses, Python constraints, artifact hashes/sizes and dependencies are retained in `06-SOURCE-EVIDENCE.json`. Package names alone are not an approval. Re-audit any version change or additional SDK/image, including transitive dependencies. No new npm dependency is proposed.

| Candidate pin | Registry license declaration | Python | Source | Legitimacy |
|---|---|---|---|---|
| `onnxruntime==1.23.2` | MIT License | >=3.10 | [PyPI](https://pypi.org/pypi/onnxruntime/1.23.2/json) | [ASSUMED] |
| `numpy==2.2.6` | Copyright (c) 2005-2024, NumPy Developers. All rights reserved. Redistribution and use in source and bina | >=3.10 | [PyPI](https://pypi.org/pypi/numpy/2.2.6/json) | [ASSUMED] |
| `opencv-python-headless==4.12.0.88` | Apache 2.0 | >=3.6 | [PyPI](https://pypi.org/pypi/opencv-python-headless/4.12.0.88/json) | [ASSUMED] |
| `pyclipper==1.4.0` | MIT | >=3.10 | [PyPI](https://pypi.org/pypi/pyclipper/1.4.0/json) | [ASSUMED] |
| `shapely==2.1.2` | BSD 3-Clause | >=3.10 | [PyPI](https://pypi.org/pypi/shapely/2.1.2/json) | [ASSUMED] |
| `jieba==0.42.1` | MIT | unspecified | [PyPI](https://pypi.org/pypi/jieba/0.42.1/json) | [ASSUMED] |
| `opencc-python-reimplemented==0.1.7` | Apache License | unspecified | [PyPI](https://pypi.org/pypi/opencc-python-reimplemented/0.1.7/json) | [ASSUMED] |
| `scikit-learn==1.7.2` | BSD-3-Clause | >=3.10 | [PyPI](https://pypi.org/pypi/scikit-learn/1.7.2/json) | [ASSUMED] |
| `umap-learn==0.5.9.post2` | BSD | >=3.9 | [PyPI](https://pypi.org/pypi/umap-learn/0.5.9.post2/json) | [ASSUMED] |
| `faster-whisper==1.2.1` | MIT | >=3.9 | [PyPI](https://pypi.org/pypi/faster-whisper/1.2.1/json) | [ASSUMED] |

The selected ONNXRuntime/NumPy/OpenCV pins have compatible Linux x86-64/Python3.13 wheel metadata. OpenCV requires NumPy<2.3: 2.2.6 intentionally avoids latest-version resolver drift. Jieba is source-only in the checked release: inspect the sdist/setup path before any build. Optional native inference dependencies should be isolated in the DeepDoc build target rather than imported by ordinary API startup. UMAP brings Numba/PyNNDescent/SciPy and faster-whisper brings CTranslate2/PyAV/tokenizers; review and lock the complete tree before install, not only these direct names. The candidate table is not a statement that the combined resolution or runtime has passed.

## Validation Architecture

Use existing pytest unit/integration/e2e/serial/live_model markers, Vitest unit/live and the real Chrome CDP helper. No new runner. Each plan creates failing meaningful fixtures/tests before production code and has exact commands in `06-VALIDATION.md`. Quick pure tests target <=120 s; real OCR/native/table/ASR, rebuilds and full tiers are explicit long-running exceptions. All waiting uses deadline polling or synchronization, never fixed sleeps. Missing approved model/service/key fails its selected real integration tier, never skips or becomes a zero-output pass.

Wave 0 fixtures: original scanned PDF with planted text, two-column PDF, rotated/cropped pages, table with spans, duplicated figures, each of fourteen strategy fixtures, Markdown/JSON/EPUB/CSV/MIME samples and a licensed short WAV/MP3 with ground-truth transcript. Geometry tests assert transform round trips and IoU/region bounds; semantics assert exact planted facts/boundaries, not simply non-empty output. Fix the corpus and thresholds before model choice. Test empty/corrupt/decompression-bomb/XXE/oversize inputs, lost lock, cancellation, dependency outage and rollback. Every added route is checked in the existing permission/matrix/leak machinery.

Before gate: all Python/frontend/Go tiers, generated checks, CI, security/async lint and no-sleep pass; serial runs alone then stack restoration, then one budgeted Phase 6 live run. Preserve earlier paid Phase 5 results, do not invoke the entire live_model marker blindly. Proposed Phase 6 cap to be approved: chat-class20, vision6, cloud OCR6, local ASR3, external adapter submit8 maximum (one per configured backend with fixed one-page fixture), query embeddings12, total ingested/summarized chunks200. Budgets include provider-save probes and retries; counters increment before calls, no broad automatic paid rerun. A provider requiring separate new credentials blocks that selected real case and is reported honestly.

Manual-only: OCR/read-order/table quality on the retained fixture pages, word-level highlight alignment, Chinese copy and two real-document answer judgments; keep Phase 5 and B-36 handoffs distinct. Package/model approval checkpoints include automated audit-file/manifest checks but no script can stand in for the human decision. Nyquist flags remain false until execution/coverage conditions are actually met; do not fake blanket compliance.

## Planning resolution and remaining uncertainties

Resolved for planning: exact existing seams; all 58 requirements; model filenames/revisions/hash metadata; CPU candidate packages; coordinate and authorization contracts; complete strategy/backend inventory; UI inheritance and testing approach. Remaining execution gates: direct/transitive package legitimacy, artifact-specific provenance, measured CPU/RSS/accuracy, backend credentials/real dialect fixtures and explicit live budget acceptance. Each has an owner/checkpoint plan; none is silently excluded from the final phase claim. No implementation is approved merely by writing this research.

### Registry legitimacy detail

| Package | Registry | Age (selected release date, not project age) | Downloads | Source Repo | slopcheck | Disposition |
|---|---|---|---|---|---|---|
| onnxruntime==1.23.2 | PyPI | release 2025-10-22 | not queried | https://onnxruntime.ai | OK | [ASSUMED]; blocking-human acceptance |
| numpy==2.2.6 | PyPI | release 2025-05-17 | not queried | see source evidence | OK | [ASSUMED]; blocking-human acceptance |
| opencv-python-headless==4.12.0.88 | PyPI | release 2025-07-07 | not queried | https://github.com/opencv/opencv-python | OK | [ASSUMED]; blocking-human acceptance |
| pyclipper==1.4.0 | PyPI | release 2025-12-01 | not queried | https://github.com/fonttools/pyclipper | OK | [ASSUMED]; blocking-human acceptance |
| shapely==2.1.2 | PyPI | release 2025-09-24 | not queried | see source evidence | OK | [ASSUMED]; blocking-human acceptance |
| jieba==0.42.1 | PyPI | release not retain | not queried | https://github.com/fxsjy/jieba | OK | [ASSUMED]; blocking-human acceptance |
| opencc-python-reimplemented==0.1.7 | PyPI | release 2023-02-11 | not queried | https://github.com/yichen0831/opencc-python | OK | [ASSUMED]; blocking-human acceptance |
| scikit-learn==1.7.2 | PyPI | release 2025-09-09 | not queried | see source evidence | OK | [ASSUMED]; blocking-human acceptance |
| umap-learn==0.5.9.post2 | PyPI | release 2025-07-03 | not queried | http://github.com/lmcinnes/umap | OK | [ASSUMED]; blocking-human acceptance |
| faster-whisper==1.2.1 | PyPI | release 2025-10-31 | not queried | https://github.com/SYSTRAN/faster-whisper | OK | [ASSUMED]; blocking-human acceptance |

No SLOP packages were reported. Transitive scan retains SUS similarity warnings for httpx2, numba and sympy; official-source identity context and exact pinned metadata are in06-PACKAGES.md. Read-only wheel-only resolution succeeded for40 packages; source-only Jieba was not built. This updates the earlier unresolved-resolver statement: metadata resolution passed, runtime/combined app environment compatibility remains unmeasured. Install only isolated approved optional groups; first inspect a whole-app dry-run diff if a dependency enters the shared application environment.
