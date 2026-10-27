# Phase 6 multi-source planning audit

Checked2026-10-27.58/58 primary requirements have a non-gate feature owner; final gate coverage is additional evidence, not the sole owner. All five goal criteria, research constraints and the RETR-13 producer handoff are covered. No CONTEXT decision was invented.

| Source | ID | Feature / constraint | Plans | Status |
|---|---|---|---|---|
| REQ | CHUNK-03 | `paper`: section-aware (Abstract, Introduction, Method, ..., References) | 06-11 | COVERED |
| REQ | CHUNK-04 | `book`: chapter/section hierarchy from headings or TOC depth | 06-10 | COVERED |
| REQ | CHUNK-05 | `laws`: Chapter / Section / Article / Item hierarchy | 06-12 | COVERED |
| REQ | CHUNK-06 | `presentation`: one chunk group per slide with slide title appended | 06-13 | COVERED |
| REQ | CHUNK-07 | `table`: one chunk per row prefixed with table title and column headers | 06-14 | COVERED |
| REQ | CHUNK-08 | `qa`: question/answer pairs from Excel/CSV/text; question stored in `question_tks` | 06-09 | COVERED |
| REQ | CHUNK-09 | `resume`: structured CV entities (name, contact, work history, education, skills) | 06-18 | COVERED |
| REQ | CHUNK-10 | `picture`: VLM description of images indexed as chunks | 06-15 | COVERED |
| REQ | CHUNK-11 | `manual`: groups code blocks, parameter tables, subsection diagrams | 06-08 | COVERED |
| REQ | CHUNK-12 | `email`: From/To/Subject/Date/Body sections | 06-17 | COVERED |
| REQ | CHUNK-13 | `tag`: extracts tag features and tag weights | 06-19 | COVERED |
| REQ | CHUNK-14 | `one`: whole document as a single chunk | 06-07 | COVERED |
| REQ | CHUNK-15 | `audio`: ASR transcript segmented into timestamped chunks | 06-16 | COVERED |
| REQ | CHUNK-17 | Text preprocessing: full-to-half-width, traditional-to-simplified Chinese, URL/email stripping, tokenize, fine-grained tokenize, token positions — *partly delivered in Phase 4 (R-160, D-27): full-to-half-width, URL/email stripping, tokenize and token positions through the in-repo stdlib tokenizer; traditional-to-simplified conversion and the dictionary fine-grained tokenizer move to Phase 6* | 06-01, 06-12 | COVERED |
| REQ | CHUNK-22 | LLM keyword extraction per chunk populates `important_kwd` | 06-21 | COVERED |
| REQ | CHUNK-23 | LLM question proposal per chunk populates `question_tks` | 06-21 | COVERED |
| REQ | CHUNK-24 | LLM content tagging against tag sets | 06-22 | COVERED |
| REQ | CHUNK-25 | LLM auto-metadata generation (`gen_metadata`) | 06-22 | COVERED |
| REQ | CHUNK-26 | RAPTOR hierarchical summarization (cluster, summarize, index summary chunks) when enabled on the dataset | 06-01, 06-24 | COVERED |
| REQ | CHUNK-27 | Public built-in pipeline listing: `GET /api/v1/pipelines?type=builtin`, `GET /api/v1/pipelines/:id` | 06-07 | COVERED |
| REQ | CHUNK-28 | Go chunker mirrors for `naive`, `one`, `qa`, `table`, `presentation` *(Python implementation in v1; Go mirror deferred to v2)* | 06-07, 06-09, 06-13, 06-14 | COVERED |
| REQ | DEPLOY-08 | `deepdoc` profile running the layout-parsing service on 9390 | 06-01, 06-02 | COVERED |
| REQ | DOC-17 | User can batch-update document metadata via `PATCH /datasets/<dataset_id>/documents/metadatas` | 06-20 | COVERED |
| REQ | DOC-18 | User can fetch an extracted image via `GET /documents/images/<image_id>` | 06-05, 06-06 | COVERED |
| REQ | DOC-19 | User can fetch a generated artifact via `GET /documents/artifact/<filename>` | 06-25 | COVERED |
| REQ | ING-18 | Dataset-wide fan-out tasks using sentinel document ids | 06-23, 06-24 | COVERED |
| REQ | KB-10 | User can aggregate tags across datasets via `GET /datasets/tags/aggregation` | 06-19 | COVERED |
| REQ | KB-11 | User can list and delete tags of a dataset via `GET` / `DELETE /datasets/<dataset_id>/tags` | 06-19 | COVERED |
| REQ | KB-12 | User can fetch flattened metadata across datasets via `GET /datasets/metadata/flattened` | 06-20 | COVERED |
| REQ | KB-13 | User can read a dataset's auto-metadata configuration via `GET /datasets/<dataset_id>/metadata/config` | 06-20 | COVERED |
| REQ | KB-17 | User can delete a derived index of a dataset by type via `DELETE /datasets/<dataset_id>/<index_type>` and trace it via `GET /datasets/<dataset_id>/artifacts/alteration` | 06-25 | COVERED |
| REQ | LLM-10 | Vision (image-to-text) model type | 06-15 | COVERED |
| REQ | LLM-11 | Speech-to-text (ASR) model type | 06-16 | COVERED |
| REQ | LLM-13 | OCR model type | 06-27 | COVERED |
| REQ | LLM-32 | Prompt generators: keyword extraction, question proposal, content tagging, metadata generation, chunk formatting | 06-21, 06-22, 06-23 | COVERED |
| REQ | PARSE-04 | Layout analysis (DLA) detects regions labelled Text, Title, Figure, Figure caption, Table, Table caption, Header, Footer, Reference, Equation | 06-01, 06-04 | COVERED |
| REQ | PARSE-05 | Text boxes are assigned to layout regions at overlap ratio >= 0.4; duplicates removed by IoU NMS; regions sorted into reading order | 06-04 | COVERED |
| REQ | PARSE-06 | OCR fallback (text detection plus recognition) runs when a page's text layer is missing or corrupt | 06-01, 06-02, 06-03 | COVERED |
| REQ | PARSE-07 | Table structure recognition reconstructs cropped tables into HTML `<table>` | 06-01, 06-06 | COVERED |
| REQ | PARSE-08 | Headers and footers are filtered from chunk content | 06-04 | COVERED |
| REQ | PARSE-09 | DOCX parser: paragraphs, headings, embedded images, tables as HTML *(Python implementation in v1; Go mirror deferred to v2)* — *partly delivered in Phase 4 (R-160, D-27): paragraphs, headings and tables as HTML; embedded images are skipped and counted in the log; image handling moves to Phase 6* | 06-05 | COVERED |
| REQ | PARSE-11 | PPTX parser: slide titles, text frames, shape tables, speaker notes, images — *partly delivered in Phase 4 (R-160, D-27): slide titles, text frames, shape tables and speaker notes; images are skipped and counted in the log; image handling moves to Phase 6* | 06-05 | COVERED |
| REQ | PARSE-14 | Markdown parser | 06-08 | COVERED |
| REQ | PARSE-15 | JSON parser | 06-09 | COVERED |
| REQ | PARSE-16 | EPUB parser | 06-10 | COVERED |
| REQ | PARSE-17 | CSV ingestion | 06-09 | COVERED |
| REQ | PARSE-18 | Image files (JPG, PNG) are parsed via OCR and/or VLM description | 06-15 | COVERED |
| REQ | PARSE-19 | Embedded figures are extracted, hashed for dedup (`image2id`), captioned by a vision model, and stored | 06-05, 06-15, 06-29 | COVERED |
| REQ | PARSE-20 | Audio files (MP3, WAV) are transcribed by an ASR model | 06-01, 06-16 | COVERED |
| REQ | PARSE-21 | Email (`.eml`) parsed into From, To, Subject, Date, Body | 06-17 | COVERED |
| REQ | PARSE-22 | Pluggable external PDF parsers: Docling and MinerU wrappers | 06-26 | COVERED |
| REQ | PARSE-23 | Additional parser backends: PaddleOCR, Mistral, TCADP, SoMark, OpenDataLoader, figure parser | 06-27, 06-28, 06-29 | COVERED |
| REQ | PARSE-24 | DLA / OCR / TSR can be offloaded to a remote DeepDoc service (`DEEPDOC_URL`, `TENSORRT_DLA_SVR`; container port 9390) | 06-02, 06-03 | COVERED |
| REQ | PARSE-25 | Parsing honours the `pages` range in `parser_config` | 06-03 | COVERED |
| REQ | PARSE-26 | Go PDF and DOCX parser implementations with CGO bindings (PDFium, OfficeOxide) *(Python implementation in v1; Go mirror deferred to v2)* | 06-03 | COVERED |
| REQ | SEC-08 | Native document parsing isolated in the `deepdoc` container | 06-01, 06-02, 06-03 | COVERED |
| REQ | STOR-09 | Extracted images and table crops are stored under `{tenant_id}/{doc_id}/{img_id}.png` and `.../tables/{table_id}.png` | 06-05, 06-06 | COVERED |
| REQ | UI-14 | Parser configurator: chunk token size, delimiter, layout-model toggle, auto-keyword count — *partly delivered in Phase 4 (R-160, D-27): chunk token size and delimiter; the layout-model toggle and the auto-keyword count move to Phase 6* | 06-03, 06-04, 06-21 | COVERED |
| GOAL | SC-1 | Scanned PDF OCR/layout/table, furniture filtering, reading order and source positions | 02–06,30 | COVERED |
| GOAL | SC-2 | Every fourteen documented chunking methods selected in the real dialog with own fixture | 07–19,30 (naive retained/regressed) | COVERED |
| GOAL | SC-3 | All additional source formats, office/PDF figures, caption/dedup/authorized image endpoint | 05,08–10,15–17,29,30 | COVERED |
| GOAL | SC-4 | Opt-in keywords/questions/tagging/metadata and recursive summary retrieval | 19–25,30 | COVERED |
| GOAL | SC-5 | deepdoc profile/9390 and actual native offload via configured URL | 02–06,16,30 | COVERED |
| RESEARCH | R6-01 | Exact artifact acquisition/build-init only, license identity/bytes/hashes and CPU/RSS probes | 01–02,16,30 | COVERED |
| RESEARCH | R6-02 | Typed geometry conversion, overlap0.4, NMS and no fabricated page positions | 03–06,26–30 | COVERED |
| RESEARCH | R6-03 | Per-method configs; no naive fallback or dishonest availability | 03–04,07–19,26–30 | COVERED |
| RESEARCH | R6-04 | Bounded uploads/ZIP/XML/media; no remote resources or arbitrary native paths | 02–18,26–30 | COVERED |
| RESEARCH | R6-05 | Public static catalog is Go, tenant operations Python; all new routes registry/matrix/leak-covered | 05,07,19–20,23,25,30 | COVERED |
| RESEARCH | R6-06 | Sealed keys, correct ASR4/vision8/OCR64 flags/defaults/probes and bounded usage | 15–16,18,21–22,27,30 | COVERED |
| RESEARCH | R6-07 | Explicit dataset sentinel context/fanout/generation/cancel, no fake Document lookup | 23–25 | COVERED |
| RESEARCH | R6-08 | RAPTOR real hierarchy, source-leaf authorization/redaction and disable/delete/reparse invalidation | 24–25,30 | COVERED |
| RESEARCH | R6-09 | Eight optional parser backend inventory with distinct dialects and real prerequisites | 26–30; Figure assets/model in05/15 | COVERED |
| RESEARCH | R6-10 | Existing UI design, actual controls, workspace fencing, original source geometry | 03–30 with UI changes | COVERED |
| RESEARCH | R6-11 | Real migration/export/Go verify-only for asset/document metadata/derived mapping changes | 05,20,23,25,30 | COVERED |
| RESEARCH | R6-12 | One Phase6 live attempt with exact approved counters; prior paid evidence preserved | 01,30 | COVERED |
| RESEARCH | R6-13 | Scoped decision records; Phase5 rows exclude later phases without weakened checks | 01,30 | COVERED |
| RESEARCH | R6-14 | RETR-13 tag/PageRank producer handoff, old fusion scores unchanged when features absent | 19,30 | COVERED |
| CONTEXT | — | No Phase6 CONTEXT/discuss artifact exists; --auto uses research/requirements, no invented user decisions | All plans; approval checkpoint01 | COVERED |

Out-of-phase exclusions preserve existing decisions: Go native parser/chunker mirrors, TTS and Phase7 canvas/agents, remaining Phase5 advanced chat/retrieval/provider/UI partials and Phase4 B36. No scope is silently moved to those exclusions. All cloud/model assumptions are owned by explicit execution prerequisites; they are not real gate passes.
