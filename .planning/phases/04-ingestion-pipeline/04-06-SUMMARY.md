---
phase: 04-ingestion-pipeline
plan: 06
subsystem: ingestion
tags: [parsers, chunking, tokenizer, tiktoken, charset-normalizer]
requires:
  - phase: 04-01
    provides: common/ingest_codes.py (METHOD_ORDER, IMPLEMENTED_PARSERS)
  - phase: 04-03
    provides: upload extension allow-list
provides:
  - ParsedBlock / PageBox / ParseReport / SourceFile / ParseLimits (parser contract)
  - Chunk (chunker contract)
  - suffix router with lazy loaders and parseable()
  - TXT/MD/CSV/JSON parser
  - stdlib tokenizer and cl100k token counting
  - naive chunker and refusing chunker factory
affects: [04-07, 04-08, 04-09, worker pipeline]
tech-stack:
  added: []
  patterns: [frozen dataclasses, fixed-message typed errors, lazy loader module paths, delimiters as literal character sets]
key-files:
  created:
    - rag/parsers/{__init__,types,errors,router,txt}.py
    - rag/chunking/{__init__,types,naive,factory}.py
    - rag/nlp/{__init__,normalize,tokenizer,token_count}.py
    - test/unit_test/{test_parser_router,test_text_parser,test_naive_chunker,test_tokenizer}.py
  modified:
    - rag/llm/embedding_model.py
    - test/unit_test/test_layering.py
key-decisions:
  - "URL and email removal is done per whitespace-delimited word, not by a regex, so it is linear on any input"
  - "Token splitting uses tiktoken decode_with_offsets so multibyte characters are never cut"
  - "Blocks are joined with a newline when the previous text does not end in whitespace"
  - "overlapped_percent is clamped to 0..50"
requirements-completed: []
duration: ~40min
completed: 2026-10-17
---

# Phase 4 Plan 06: Parser and chunker contracts, TXT parser, tokenizer, naive chunker

The two shared types (`ParsedBlock`, `Chunk`), the suffix router, a charset-aware TXT parser, a stdlib tokenizer and a token-bounded naive chunker with a factory that refuses the seven unbuilt methods.

## Tasks

1. Types, router, typed errors, TXT parser - commit e862b62
2. Tokenizer, token counting, naive chunker, factory - commit 4093b7d

Both tasks were written test-first (tests failed at collection before the modules existed). 59 tests across the five files pass; `scripts/ci/run_all.py` passes 7/7 gates.

## Deviations from Plan

None in behaviour. Notes:
- RED and GREEN were committed together per task rather than as separate test/feat commits.
- `traditional-to-simplified` conversion is not performed (D-27, R-160); CHUNK-17 stays partial.
- `uv run ruff check` reports 4 pre-existing import-order errors in unrelated tests (test_llm_registry, test_local_storage, test_model_ref, test_storage_factory); not touched.

## Known Stubs

None. The router references `rag.parsers.pdf/docx/xlsx/pptx/html` loader modules that plans 04-08 and 04-09 create; they are imported lazily and not loaded by tests.

## Threat Flags

None.

## Self-Check: PASSED
- Files exist under rag/parsers, rag/chunking, rag/nlp; commits e862b62 and 4093b7d present.
