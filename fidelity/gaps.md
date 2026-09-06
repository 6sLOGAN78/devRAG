# Fidelity Gaps

## Resolved Gaps
1. **[P0] Ingestion Task Creation Bug**
   - *Issue*: `UploadDocument` failed to create `DocumentTask` records in MySQL, halting the entire indexing pipeline permanently.
   - *Fix*: Modified `internal/dao/document.go` to include `CreateDocumentWithTask` which executes a transactional insert of both `Document` and `DocumentTask`. Modified `internal/service/document.go` to use this new function.
   - *Status*: Verified. Tasks are now successfully claimed by the Syncer and dispatched to the Python ML worker.

## Unresolved Gaps
*(Will populate as inspection continues)*
2. **[P1] Storage Bucket Discrepancy**
   - *Issue*: The Go API (`internal/storage/minio.go`) uploads all documents to a hardcoded `devrag-documents` bucket. The Python `parsing_service.py` incorrectly assumed the first path segment was the bucket name (e.g., `tenant`), causing MinIO `NoSuchBucket` errors during task execution.
   - *Fix*: Patched `api/services/parsing_service.py` to correctly expect the `devrag-documents` bucket and pass the full `minio_path` as the object name.
   - *Status*: Verified. Python worker successfully downloads from MinIO, parses, and inserts chunks into Infinity.
3. **[P0] Agent Graph Engine: Missing Input Resolution and Cross-Tenant Data Vulnerability**
   - *Issue*: DevRAG's `AgentGraph` incorrectly parsed `inputs_map`, resulting in execution states failing to propagate data (like user queries) between DAG nodes. More critically, the `RetrievalNode` blindly executed vector queries against any `dataset_id` provided in the configuration without validating if the dataset belonged to the authenticated tenant, exposing a severe cross-tenant data access vulnerability.
   - *Fix*: 
     - Corrected `agent/graph.py` to properly parse `inputs_map` without overwriting it during node initialization.
     - Updated `GraphRunner` to securely inject `__tenant_id__` from the HTTP context into the resolved inputs for all nodes.
     - Patched `RetrievalNode.execute` to strictly validate `Dataset` ownership against `__tenant_id__` before proceeding with the Infinity vector search.
   - *Status*: Verified. A test chat request successfully resolves inputs, safely queries the tenant's isolated vector index, and passes the retrieved chunks to the LLM node.
4. **[P0] Missing Tenant API Key Management (TenantLLM)**
   - *Issue*: DevRAG completely lacks RAGFlow's `TenantLLM` database model and API endpoints. Currently, LLM inference relies solely on a system-wide fallback configuration (`user_default_llm`), meaning all tenants share the host's API keys for chat and embedding generation. This breaks multi-tenancy LLM billing and quota isolation.
   - *Fix*: 
     - Added `ChatModelConfig` to `user_default_llm.default_models` in `conf/service_conf.yaml` and `common/settings.py` to match RAGFlow's fallback structure.
     - Updated `LLMNode.execute` to fallback to `user_default_llm` for the API key and model factory if a tenant key is not provided.
     - *Next Step*: Implement the `TenantLLM` MySQL table, Go API endpoints for users to manage their keys, and update `LLMNode` to fetch the tenant's API key before falling back to the system default.
   - *Status*: Fallback configuration aligned with RAGFlow. TenantLLM implementation pending.
