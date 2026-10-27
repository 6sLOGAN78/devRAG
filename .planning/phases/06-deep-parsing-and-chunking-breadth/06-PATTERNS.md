# Phase 6 pattern map

Read-only mapping from the current tree,2026-10-27. Entries marked as new by their owning plan are planned paths, not existing implementations. All related tests/controllers/native modules reuse these seams; no new framework is proposed.

Concrete existing contracts:

- `rag/parsers/types.py`: `ParsedBlock(text,kind,boxes,page_sizes)`, `PageBox(page,x0,top,x1,bottom)` and parser `parse(source,report,*,page_range=None,limits=None)`.
- `rag/chunking/types.py`: `Chunk(text,positions,page_sizes,token_num,index)`; `rag/chunking/factory.py`: `_CHUNKERS` plus `get_chunker(parser_id)` refuses unbuilt methods.
- `rag/svr/pipeline.py`: `PipelineDeps(settings,storage,doc_store,embedder,limiters)`; `_index_batches` checks current document/task switches before publish and treats a nonempty insert result as failure.
- `api/apps/restful_apis/chunk_api.py`: Pydantic `extra="forbid"`, fixed `ServiceError` mapping, named DB/DOCSTORE/PROVIDER executors and bounded authorization/read/write deadlines.
- `api/db/services/llm_service.py::_report_usage`: counts atomic tenant/model usage and logs only IDs/model/provider/counts. Preserve no source/answer/key logging.
- `api/db/models/identity.py::Tenant` already has `asr_id/tenant_asr_id`, `img2txt_id/tenant_img2txt_id`, `ocr_id/tenant_ocr_id`; use these actual fields before proposing a new default-model column. Existing tenant model bits are chat1,embedding2,rerank16; use the existing documented bits ASR4,vision8,OCR64, reserving32 for TTS, with explicit no-collision/old-row decode tests.
- `web/src/services/chunk-service.ts`: typed explicit-field mappers, finite geometry, bounded page sizes. Its pixel-space comment must be reconciled with the actual PagePreview dimensions through existing geometry tests, not used as evidence to multiply coordinates twice.
- Existing form/controller/route artifacts are in06-CONTRACTS.md. All generated destinations are discovered from the current generator scripts before execution.

| Planned/modified file | Role | Closest existing analog | Reused contract / important difference |
|---|---|---|---|
| `.planning/DECISIONS.md` | configuration/evidence/guard | `common/settings.py; scripts/ci/check_generated.py` | typed catalog/default parity and explicit non-secret evidence |
| `.planning/phases/06-deep-parsing-and-chunking-breadth/06-GATE-LOG.md` | configuration/evidence/guard | `common/settings.py; scripts/ci/check_generated.py` | typed catalog/default parity and explicit non-secret evidence |
| `.planning/phases/06-deep-parsing-and-chunking-breadth/06-HUMAN-UAT.md` | configuration/evidence/guard | `common/settings.py; scripts/ci/check_generated.py` | typed catalog/default parity and explicit non-secret evidence |
| `.planning/phases/06-deep-parsing-and-chunking-breadth/06-VALIDATION.md` | configuration/evidence/guard | `common/settings.py; scripts/ci/check_generated.py` | typed catalog/default parity and explicit non-secret evidence |
| `api/apps/restful_apis/dataset_artifact_api.py` | Python authenticated controller | `api/apps/restful_apis/chunk_api.py` | Pydantic body/envelope, named executors, service-first authorization, fixed responses |
| `api/apps/restful_apis/dataset_job_api.py` | Python authenticated controller | `api/apps/restful_apis/chunk_api.py` | Pydantic body/envelope, named executors, service-first authorization, fixed responses |
| `api/apps/restful_apis/dataset_tag_api.py` | Python authenticated controller | `api/apps/restful_apis/chunk_api.py` | Pydantic body/envelope, named executors, service-first authorization, fixed responses |
| `api/apps/restful_apis/document_asset_api.py` | Python authenticated controller | `api/apps/restful_apis/chunk_api.py` | Pydantic body/envelope, named executors, service-first authorization, fixed responses |
| `api/apps/restful_apis/document_metadata_api.py` | Python authenticated controller | `api/apps/restful_apis/chunk_api.py` | Pydantic body/envelope, named executors, service-first authorization, fixed responses |
| `api/db/models/knowledge.py` | Peewee schema owner | `api/db/models/knowledge.py; api/db/migrations/0003_chat_assistants.py` | real migration/export/Go verify-only parity, not an alternate ORM push |
| `api/db/services/chat_turn_reference.py` | scoped domain service | `api/db/services/chunk_service.py; api/db/services/tenant_scope.py` | authorized dataset/document context before storage/model/index access |
| `api/db/services/chunk_view.py` | scoped domain service | `api/db/services/chunk_service.py; api/db/services/tenant_scope.py` | authorized dataset/document context before storage/model/index access |
| `api/db/services/dataset_artifact_service.py` | scoped domain service | `api/db/services/chunk_service.py; api/db/services/tenant_scope.py` | authorized dataset/document context before storage/model/index access |
| `api/db/services/dataset_job_service.py` | scoped domain service | `api/db/services/chunk_service.py; api/db/services/tenant_scope.py` | authorized dataset/document context before storage/model/index access |
| `api/db/services/knowledgebase_service.py` | scoped domain service | `api/db/services/chunk_service.py; api/db/services/tenant_scope.py` | authorized dataset/document context before storage/model/index access |
| `api/db/services/dataset_tag_service.py` | scoped domain service | `api/db/services/chunk_service.py; api/db/services/tenant_scope.py` | authorized dataset/document context before storage/model/index access |
| `api/db/services/document_asset_service.py` | scoped domain service | `api/db/services/chunk_service.py; api/db/services/tenant_scope.py` | authorized dataset/document context before storage/model/index access |
| `api/db/services/document_metadata_service.py` | scoped domain service | `api/db/services/chunk_service.py; api/db/services/tenant_scope.py` | authorized dataset/document context before storage/model/index access |
| `api/db/services/document_service.py` | scoped domain service | `api/db/services/chunk_service.py; api/db/services/tenant_scope.py` | authorized dataset/document context before storage/model/index access |
| `api/db/services/document_view.py` | scoped domain service | `api/db/services/chunk_service.py; api/db/services/tenant_scope.py` | authorized dataset/document context before storage/model/index access |
| `api/db/services/llm_service.py` | scoped domain service | `api/db/services/chunk_service.py; api/db/services/tenant_scope.py` | authorized dataset/document context before storage/model/index access |
| `api/db/services/parser_config.py` | scoped domain service | `api/db/services/chunk_service.py; api/db/services/tenant_scope.py` | authorized dataset/document context before storage/model/index access |
| `api/db/services/provider_service.py` | scoped domain service | `api/db/services/chunk_service.py; api/db/services/tenant_scope.py` | authorized dataset/document context before storage/model/index access |
| `api/db/services/retrieval_service.py` | scoped domain service | `api/db/services/chunk_service.py; api/db/services/tenant_scope.py` | authorized dataset/document context before storage/model/index access |
| `api/db/services/task_service.py` | scoped domain service | `api/db/services/chunk_service.py; api/db/services/tenant_scope.py` | authorized dataset/document context before storage/model/index access |
| `common/ingest_codes.py` | configuration/evidence/guard | `common/settings.py; scripts/ci/check_generated.py` | typed catalog/default parity and explicit non-secret evidence |
| `common/settings.py` | configuration/evidence/guard | `common/settings.py; scripts/ci/check_generated.py` | typed catalog/default parity and explicit non-secret evidence |
| `conf/routes.yaml` | configuration/evidence/guard | `common/settings.py; scripts/ci/check_generated.py` | typed catalog/default parity and explicit non-secret evidence |
| `deepdoc/asr.py` | native isolated parse/inference | `rag/parsers/pdf.py; api/apps/__init__.py; docker/docker-compose-base.yml` | typed bytes/blocks boundary plus existing Quart lifecycle; inference dependencies remain service-local |
| `deepdoc/geometry.py` | native isolated parse/inference | `rag/parsers/pdf.py; api/apps/__init__.py; docker/docker-compose-base.yml` | typed bytes/blocks boundary plus existing Quart lifecycle; inference dependencies remain service-local |
| `deepdoc/layout.py` | native isolated parse/inference | `rag/parsers/pdf.py; api/apps/__init__.py; docker/docker-compose-base.yml` | typed bytes/blocks boundary plus existing Quart lifecycle; inference dependencies remain service-local |
| `deepdoc/model_runtime.py` | native isolated parse/inference | `rag/parsers/pdf.py; api/apps/__init__.py; docker/docker-compose-base.yml` | typed bytes/blocks boundary plus existing Quart lifecycle; inference dependencies remain service-local |
| `deepdoc/ocr.py` | native isolated parse/inference | `rag/parsers/pdf.py; api/apps/__init__.py; docker/docker-compose-base.yml` | typed bytes/blocks boundary plus existing Quart lifecycle; inference dependencies remain service-local |
| `deepdoc/pdf.py` | native isolated parse/inference | `rag/parsers/pdf.py; api/apps/__init__.py; docker/docker-compose-base.yml` | typed bytes/blocks boundary plus existing Quart lifecycle; inference dependencies remain service-local |
| `deepdoc/server.py` | native isolated parse/inference | `rag/parsers/pdf.py; api/apps/__init__.py; docker/docker-compose-base.yml` | typed bytes/blocks boundary plus existing Quart lifecycle; inference dependencies remain service-local |
| `deepdoc/tables.py` | native isolated parse/inference | `rag/parsers/pdf.py; api/apps/__init__.py; docker/docker-compose-base.yml` | typed bytes/blocks boundary plus existing Quart lifecycle; inference dependencies remain service-local |
| `docker/Dockerfile.deepdoc` | configuration/evidence/guard | `common/settings.py; scripts/ci/check_generated.py` | typed catalog/default parity and explicit non-secret evidence |
| `docker/docker-compose-base.yml` | configuration/evidence/guard | `common/settings.py; scripts/ci/check_generated.py` | typed catalog/default parity and explicit non-secret evidence |
| `docker/docker-compose.dev.yml` | configuration/evidence/guard | `common/settings.py; scripts/ci/check_generated.py` | typed catalog/default parity and explicit non-secret evidence |
| `internal/handler/pipeline.go` | Go static public template catalog | `internal/handler/system.go; internal/router/router.go` | registry-generated exact public read policy, static credential-free data, Go ownership per docs |
| `internal/pipeline/builtin.go` | Go static public template catalog | `internal/handler/system.go; internal/router/router.go` | registry-generated exact public read policy, static credential-free data, Go ownership per docs |
| `internal/router/router.go` | Go static public template catalog | `internal/handler/system.go; internal/router/router.go` | registry-generated exact public read policy, static credential-free data, Go ownership per docs |
| `rag/advanced_rag/raptor.py` | leased ingestion/derived generation | `rag/svr/pipeline.py; rag/svr/control.py; rag/svr/progress.py` | current task/generation checks, DB release before inference, checked index writes, final publish ordering |
| `rag/chunking/audio.py` | structural chunk transform | `rag/chunking/naive.py; rag/chunking/types.py` | typed Chunk output, deterministic order/source geometry, method factory dispatch |
| `rag/chunking/book.py` | structural chunk transform | `rag/chunking/naive.py; rag/chunking/types.py` | typed Chunk output, deterministic order/source geometry, method factory dispatch |
| `rag/chunking/email.py` | structural chunk transform | `rag/chunking/naive.py; rag/chunking/types.py` | typed Chunk output, deterministic order/source geometry, method factory dispatch |
| `rag/chunking/factory.py` | structural chunk transform | `rag/chunking/naive.py; rag/chunking/types.py` | typed Chunk output, deterministic order/source geometry, method factory dispatch |
| `rag/chunking/laws.py` | structural chunk transform | `rag/chunking/naive.py; rag/chunking/types.py` | typed Chunk output, deterministic order/source geometry, method factory dispatch |
| `rag/chunking/manual.py` | structural chunk transform | `rag/chunking/naive.py; rag/chunking/types.py` | typed Chunk output, deterministic order/source geometry, method factory dispatch |
| `rag/chunking/naive.py` | structural chunk transform | `rag/chunking/naive.py; rag/chunking/types.py` | typed Chunk output, deterministic order/source geometry, method factory dispatch |
| `rag/chunking/one.py` | structural chunk transform | `rag/chunking/naive.py; rag/chunking/types.py` | typed Chunk output, deterministic order/source geometry, method factory dispatch |
| `rag/chunking/paper.py` | structural chunk transform | `rag/chunking/naive.py; rag/chunking/types.py` | typed Chunk output, deterministic order/source geometry, method factory dispatch |
| `rag/chunking/picture.py` | structural chunk transform | `rag/chunking/naive.py; rag/chunking/types.py` | typed Chunk output, deterministic order/source geometry, method factory dispatch |
| `rag/chunking/presentation.py` | structural chunk transform | `rag/chunking/naive.py; rag/chunking/types.py` | typed Chunk output, deterministic order/source geometry, method factory dispatch |
| `rag/chunking/qa.py` | structural chunk transform | `rag/chunking/naive.py; rag/chunking/types.py` | typed Chunk output, deterministic order/source geometry, method factory dispatch |
| `rag/chunking/resume.py` | structural chunk transform | `rag/chunking/naive.py; rag/chunking/types.py` | typed Chunk output, deterministic order/source geometry, method factory dispatch |
| `rag/chunking/table.py` | structural chunk transform | `rag/chunking/naive.py; rag/chunking/types.py` | typed Chunk output, deterministic order/source geometry, method factory dispatch |
| `rag/chunking/tag.py` | structural chunk transform | `rag/chunking/naive.py; rag/chunking/types.py` | typed Chunk output, deterministic order/source geometry, method factory dispatch |
| `rag/llm/__init__.py` | tenant model driver | `rag/llm/rerank_model.py; api/db/services/llm_service.py` | ProviderSpec capability, sealed key, reset/report usage, typed errors and deadlines |
| `rag/llm/asr_model.py` | tenant model driver | `rag/llm/rerank_model.py; api/db/services/llm_service.py` | ProviderSpec capability, sealed key, reset/report usage, typed errors and deadlines |
| `rag/llm/ocr_model.py` | tenant model driver | `rag/llm/rerank_model.py; api/db/services/llm_service.py` | ProviderSpec capability, sealed key, reset/report usage, typed errors and deadlines |
| `rag/llm/vision_model.py` | tenant model driver | `rag/llm/rerank_model.py; api/db/services/llm_service.py` | ProviderSpec capability, sealed key, reset/report usage, typed errors and deadlines |
| `rag/nlp/fusion.py` | configuration/evidence/guard | `common/settings.py; scripts/ci/check_generated.py` | typed catalog/default parity and explicit non-secret evidence |
| `rag/nlp/query.py` | configuration/evidence/guard | `common/settings.py; scripts/ci/check_generated.py` | typed catalog/default parity and explicit non-secret evidence |
| `rag/nlp/search.py` | configuration/evidence/guard | `common/settings.py; scripts/ci/check_generated.py` | typed catalog/default parity and explicit non-secret evidence |
| `rag/nlp/tokenizer.py` | configuration/evidence/guard | `common/settings.py; scripts/ci/check_generated.py` | typed catalog/default parity and explicit non-secret evidence |
| `rag/parsers/audio.py` | source parser | `rag/parsers/docx.py; rag/parsers/txt.py; rag/parsers/types.py` | same parse(source,report,page_range,limits) contract and safe source-format limits |
| `rag/parsers/backend_registry.py` | source parser | `rag/parsers/docx.py; rag/parsers/txt.py; rag/parsers/types.py` | same parse(source,report,page_range,limits) contract and safe source-format limits |
| `rag/parsers/backends/docling.py` | provider-specific transport normalization | `rag/llm/rerank_model.py; common/net/url_guard.py` | bounded httpx requests, explicit parsing, guarded URL, typed refusal; no silent fallback |
| `rag/parsers/backends/figure.py` | provider-specific transport normalization | `rag/llm/rerank_model.py; common/net/url_guard.py` | bounded httpx requests, explicit parsing, guarded URL, typed refusal; no silent fallback |
| `rag/parsers/backends/mineru.py` | provider-specific transport normalization | `rag/llm/rerank_model.py; common/net/url_guard.py` | bounded httpx requests, explicit parsing, guarded URL, typed refusal; no silent fallback |
| `rag/parsers/backends/mistral.py` | provider-specific transport normalization | `rag/llm/rerank_model.py; common/net/url_guard.py` | bounded httpx requests, explicit parsing, guarded URL, typed refusal; no silent fallback |
| `rag/parsers/backends/opendataloader.py` | provider-specific transport normalization | `rag/llm/rerank_model.py; common/net/url_guard.py` | bounded httpx requests, explicit parsing, guarded URL, typed refusal; no silent fallback |
| `rag/parsers/backends/paddleocr.py` | provider-specific transport normalization | `rag/llm/rerank_model.py; common/net/url_guard.py` | bounded httpx requests, explicit parsing, guarded URL, typed refusal; no silent fallback |
| `rag/parsers/backends/somark.py` | provider-specific transport normalization | `rag/llm/rerank_model.py; common/net/url_guard.py` | bounded httpx requests, explicit parsing, guarded URL, typed refusal; no silent fallback |
| `rag/parsers/backends/tcadp.py` | provider-specific transport normalization | `rag/llm/rerank_model.py; common/net/url_guard.py` | bounded httpx requests, explicit parsing, guarded URL, typed refusal; no silent fallback |
| `rag/parsers/csv.py` | source parser | `rag/parsers/docx.py; rag/parsers/txt.py; rag/parsers/types.py` | same parse(source,report,page_range,limits) contract and safe source-format limits |
| `rag/parsers/deepdoc_client.py` | source parser | `rag/parsers/docx.py; rag/parsers/txt.py; rag/parsers/types.py` | same parse(source,report,page_range,limits) contract and safe source-format limits |
| `rag/parsers/docx.py` | source parser | `rag/parsers/docx.py; rag/parsers/txt.py; rag/parsers/types.py` | same parse(source,report,page_range,limits) contract and safe source-format limits |
| `rag/parsers/email.py` | source parser | `rag/parsers/docx.py; rag/parsers/txt.py; rag/parsers/types.py` | same parse(source,report,page_range,limits) contract and safe source-format limits |
| `rag/parsers/epub.py` | source parser | `rag/parsers/docx.py; rag/parsers/txt.py; rag/parsers/types.py` | same parse(source,report,page_range,limits) contract and safe source-format limits |
| `rag/parsers/image.py` | source parser | `rag/parsers/docx.py; rag/parsers/txt.py; rag/parsers/types.py` | same parse(source,report,page_range,limits) contract and safe source-format limits |
| `rag/parsers/json.py` | source parser | `rag/parsers/docx.py; rag/parsers/txt.py; rag/parsers/types.py` | same parse(source,report,page_range,limits) contract and safe source-format limits |
| `rag/parsers/limits.py` | source parser | `rag/parsers/docx.py; rag/parsers/txt.py; rag/parsers/types.py` | same parse(source,report,page_range,limits) contract and safe source-format limits |
| `rag/parsers/markdown.py` | source parser | `rag/parsers/docx.py; rag/parsers/txt.py; rag/parsers/types.py` | same parse(source,report,page_range,limits) contract and safe source-format limits |
| `rag/parsers/pdf.py` | source parser | `rag/parsers/docx.py; rag/parsers/txt.py; rag/parsers/types.py` | same parse(source,report,page_range,limits) contract and safe source-format limits |
| `rag/parsers/pptx.py` | source parser | `rag/parsers/docx.py; rag/parsers/txt.py; rag/parsers/types.py` | same parse(source,report,page_range,limits) contract and safe source-format limits |
| `rag/parsers/router.py` | source parser | `rag/parsers/docx.py; rag/parsers/txt.py; rag/parsers/types.py` | same parse(source,report,page_range,limits) contract and safe source-format limits |
| `rag/parsers/tabletext.py` | source parser | `rag/parsers/docx.py; rag/parsers/txt.py; rag/parsers/types.py` | same parse(source,report,page_range,limits) contract and safe source-format limits |
| `rag/parsers/types.py` | source parser | `rag/parsers/docx.py; rag/parsers/txt.py; rag/parsers/types.py` | same parse(source,report,page_range,limits) contract and safe source-format limits |
| `rag/prompts/enrichment.py` | configuration/evidence/guard | `common/settings.py; scripts/ci/check_generated.py` | typed catalog/default parity and explicit non-secret evidence |
| `rag/svr/chunk_doc.py` | leased ingestion/derived generation | `rag/svr/pipeline.py; rag/svr/control.py; rag/svr/progress.py` | current task/generation checks, DB release before inference, checked index writes, final publish ordering |
| `rag/svr/dataset_jobs.py` | leased ingestion/derived generation | `rag/svr/pipeline.py; rag/svr/control.py; rag/svr/progress.py` | current task/generation checks, DB release before inference, checked index writes, final publish ordering |
| `rag/svr/enrichment.py` | leased ingestion/derived generation | `rag/svr/pipeline.py; rag/svr/control.py; rag/svr/progress.py` | current task/generation checks, DB release before inference, checked index writes, final publish ordering |
| `rag/svr/pipeline.py` | leased ingestion/derived generation | `rag/svr/pipeline.py; rag/svr/control.py; rag/svr/progress.py` | current task/generation checks, DB release before inference, checked index writes, final publish ordering |
| `rag/svr/progress.py` | leased ingestion/derived generation | `rag/svr/pipeline.py; rag/svr/control.py; rag/svr/progress.py` | current task/generation checks, DB release before inference, checked index writes, final publish ordering |
| `rag/svr/task_executor.py` | leased ingestion/derived generation | `rag/svr/pipeline.py; rag/svr/control.py; rag/svr/progress.py` | current task/generation checks, DB release before inference, checked index writes, final publish ordering |
| `rag/utils/storage_base.py` | configuration/evidence/guard | `common/settings.py; scripts/ci/check_generated.py` | typed catalog/default parity and explicit non-secret evidence |
| `scripts/provision_deepdoc.py` | configuration/evidence/guard | `common/settings.py; scripts/ci/check_generated.py` | typed catalog/default parity and explicit non-secret evidence |
| `test/testcases/test_live_phase6.py` | configuration/evidence/guard | `common/settings.py; scripts/ci/check_generated.py` | typed catalog/default parity and explicit non-secret evidence |
| `test/testcases/test_spa_phase6_browser.py` | configuration/evidence/guard | `common/settings.py; scripts/ci/check_generated.py` | typed catalog/default parity and explicit non-secret evidence |
| `test/unit_test/test_phase6_records.py` | configuration/evidence/guard | `common/settings.py; scripts/ci/check_generated.py` | typed catalog/default parity and explicit non-secret evidence |
| `test/unit_test/test_phase6_traceability.py` | configuration/evidence/guard | `common/settings.py; scripts/ci/check_generated.py` | typed catalog/default parity and explicit non-secret evidence |
| `web/src/components/chunk-method-dialog/chunk-method-form.tsx` | existing workspace UI | `web/src/components/parse-configuration/index.tsx; web/src/components/source-drawer/index.tsx` | typed service mapping, inherited theme, workspace-fenced query keys, focus/draft guards |
| `web/src/components/parse-configuration/index.tsx` | existing workspace UI | `web/src/components/parse-configuration/index.tsx; web/src/components/source-drawer/index.tsx` | typed service mapping, inherited theme, workspace-fenced query keys, focus/draft guards |
| `web/src/components/parse-configuration/schema.ts` | existing workspace UI | `web/src/components/parse-configuration/index.tsx; web/src/components/source-drawer/index.tsx` | typed service mapping, inherited theme, workspace-fenced query keys, focus/draft guards |
| `web/src/components/source-drawer/index.tsx` | existing workspace UI | `web/src/components/parse-configuration/index.tsx; web/src/components/source-drawer/index.tsx` | typed service mapping, inherited theme, workspace-fenced query keys, focus/draft guards |
| `web/src/constants/chunk-methods.ts` | existing workspace UI | `web/src/components/parse-configuration/index.tsx; web/src/components/source-drawer/index.tsx` | typed service mapping, inherited theme, workspace-fenced query keys, focus/draft guards |
| `web/src/pages/dataset/derived-jobs.tsx` | existing workspace UI | `web/src/components/parse-configuration/index.tsx; web/src/components/source-drawer/index.tsx` | typed service mapping, inherited theme, workspace-fenced query keys, focus/draft guards |
| `web/src/pages/dataset/metadata.tsx` | existing workspace UI | `web/src/components/parse-configuration/index.tsx; web/src/components/source-drawer/index.tsx` | typed service mapping, inherited theme, workspace-fenced query keys, focus/draft guards |
| `web/src/pages/dataset/selection-bar.tsx` | existing workspace UI | `web/src/components/parse-configuration/index.tsx; web/src/components/source-drawer/index.tsx` | typed service mapping, inherited theme, workspace-fenced query keys, focus/draft guards |
| `web/src/pages/dataset/tags.tsx` | existing workspace UI | `web/src/components/parse-configuration/index.tsx; web/src/components/source-drawer/index.tsx` | typed service mapping, inherited theme, workspace-fenced query keys, focus/draft guards |
