---
phase: 06-deep-parsing-and-chunking-breadth
plan: "08"
subsystem: markdown-and-manuals
requirements-completed: []
---

# Plan06-08: Ingest Markdown and technical manuals

Markdown/MD now use a bounded structural parser for ATX/setext headings, paragraphs, lists, pipe tables, variable-length fenced code and literal image descriptors. Source text and complete code fences remain intact. Heading levels and one-based source-line ranges are typed/defaulted; no PDF coordinates are fabricated. Unclosed fences retain the entire remaining source with a fixed note. Per-line/text/line-count/block-count limits refuse safely. No code is executed and no linked local/remote resource is fetched or decoded.

Manual is a real section-aware chunker with its own config. Code, parameter tables and related diagram descriptors remain with their subsection; unrelated sections separate. Ancestor/current heading context repeats when long prose splits to its soft token budget. Atomic groups preserve code/table/image references and existing source geometry, then refuse beyond context rather than truncate or split code. The actual model context is checked before encode. Defaulted source-line metadata survives General/One and indexing while their existing text boundaries remain compatible. Invalid input never selects a naive fallback.

The existing method dialog saves/reopens Manual; Python/frontend/static Go template availability agree. The source drawer safely renders original Markdown headings/code/GFM tables through existing react-markdown/remark-gfm/CodeBlock, without citation rewriting, raw HTML or request-capable images. Diagram descriptions remain readable text. Markdown previews have more height; other formats retain their previous view. Actual Chrome shows complete literal code, planted52/9100 and its parameter table together. Opening the separate calibration section proves hostile HTML stays inert; the code is identical after index/read. Screenshot review is assistant verification, not human UAT approval.

Verification: full root unit2553passed/8existing skips, frontend2160passed107files, final focused61passed, Go internal allpass. Final rebuilt native/parser/One/Manual and actual table/One/Manual browser regressions28passed; affected real services55passed; route/OpenAPI70passed; response/log leaks6passed. CI7/7/security/generated/admission pass. Oversize atomic Manual content refuses before any provider or index write. See06-08-VERIFICATION.json and complete06-08-FILES.txt.

## Deviations and review

Supplemental glue was assigned before edits in06-08-PROGRESS: typed heading/source-line fields, index metadata, default metadata retention, method config/availability, static Go parity, actual embedding-context refusal and safe original source rendering. Existing snapshots declaring Markdown-as-TXT or Manual-unbuilt were updated to the built implementation; other unavailable methods still refuse and Manual/One explicitly differ from naive.

Retained meaningful REDs cover routing/Manual absence, source rendering, indented backticks that closed code too early, pipe-bearing headings swallowed by a table and later prose chunks losing the immediate subsection. These were fixed in their owning code without changing original fixtures or assertions. A CDP DOM-object predicate was a test setup error; converting it to Boolean retained exact code/table/security checks. Screenshot capture now waits for actual animation/viewport bounds through existing polling. An initial unrelated chat focus failure passed focused18 and a fresh full2160 without changing chat code/tests. Interrupted pre-reboot jobs are not counted as passes.

The host reboot stopped jobs/services and reset the map limit. The full approved stack was restored; vm.max_map_count is measured262144. Current app/worker use a recorded one-off recipe atop the exact verified local runtime with identical pyproject/uv.lock hashes, while current Go/web/source are rebuilt normally. Native reuses the unchanged approved vendor cache. Standard product Dockerfiles remain unchanged; no new dependency/model or external parser image. Prior cache-only cleanup approval remains scoped and durable.

R-239 is accepted automatically, not user-reviewed. REQUIREMENTS.md is unchanged. Next09 adds structured JSON/CSV and Q&A pairs; Go parsing/chunking runtime mirrors remain deferred. Phase5 final human acceptance, Phase4 B36 and the full Phase6 gate/user UAT remain separate/pending.
