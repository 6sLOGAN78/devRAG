# Additional Plan 03 glue and sequencing review

The implemented transport changes require callers/types/config/test mirrors beyond the original four-file task budget. This explicit supplemental breakdown assigns them to narrow review units; no new package, model, schema migration or paid call is introduced.

1. Native transport: deepdoc/pdf_service.py, deepdoc/native_runtime.py, deepdoc/server.py, rag/parsers/deepdoc_client.py. Byte-only authenticated endpoints, strict bounded options, named single native executor and typed failures. Native PDF implementation moved from the previous facade, preserving geometry.
2. API preview/count glue: api/db/services/pdf_pages.py, page_service.py, document_view.py and api/apps/restful_apis/document_api.py. Authorization stays before storage/native transport; full source page count is distinct from selected-page task summaries; pages enter the explicit DTO.
3. Task/config glue: api/db/services/ingestion_service.py, parser_config.py, task_service.py and rag/chunking/factory.py. One-based inclusive ranges are validated, merged and split; settings affect task digest; per-method configuration moves into its factory without aliasing unavailable methods.
4. Existing pipeline/build wiring: rag/svr/pipeline.py, Dockerfile, docker/docker-compose.yml and test/unit_test/test_compose_files.py. App/worker attach to native network; all PDF operations take configured settings; no global native imports in either process.
5. Form integration: web/src/components/chunk-method-dialog/{chunk-method-form,index}.tsx, web/src/components/parse-configuration/{index.tsx,schema.ts}. Page ranges are persisted without overwriting unrelated settings.
6. Frontend transport: web/src/services/{mapping,document-service,dataset-service}.ts and web/src/pages/dataset/errors.ts. Explicit bounded DTO mapping and field-specific error mapping.
7. Test mirrors: web/src/test/server-areas/{files,document-settings}.ts plus focused form/dialog tests. Actual Chrome checks independently exercise the real stack, rather than relying on the test server.
8. Failure codes/copy: common/ingest_codes.py, web/src/constants/failure-codes.ts and en/zh failures locale areas; stale copy saying scans are unsupported becomes the neutral no-readable-text message. Affected existing copy assertions are updated, retaining their failure/state assertions.
9. Generated OpenAPI JSON/declarations use scripts/export_openapi.py and npm run gen:api. No DB schema or route policy changes.

Plan 03 cannot honestly activate layout before Plan 04's detector exists. Execute its remote PDF/page-selection prerequisite and verify it first, then implement Plan 04's detector and activate the saved layout control, then close both declared criteria. Until then no 03 SUMMARY, R234 or completion count is earned. Native requests explicitly asking for unavailable layout receive a typed refusal rather than silently returning text-only success. The accepted pinned model's ten artifact classes require an explicit adapter to the documented eleven semantic labels during 04; the acceptance/licenses/hashes are unchanged.

Publication is authorized by the user's subsequent “push t github too”; obsolete no-commit prose in older plans is superseded. No force push, branch change or requirement-checkbox edits are authorized or needed.
