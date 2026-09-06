from common.settings import load_config
import os
import logging
from typing import List
from api.db.db_models import DocumentChunk
from rag.vector_store.base import VectorRecord
from rag.vector_store.infinity_adapter import InfinityAdapter
from rag.nlp.embedding import EmbeddingEngine, EmbeddingConfig

logger = logging.getLogger(__name__)

class IndexingService:
    def __init__(self):
        # Initialize lazily to avoid connecting on import
        self._vector_store = None

    @property
    def vector_store(self):
        if self._vector_store is None:
            self._vector_store = InfinityAdapter()
        return self._vector_store

    def _get_embedding_config(self, dataset_id: str) -> EmbeddingConfig:
        from api.db.db_models import Dataset, TenantLLM
        cfg = load_config(os.environ.get('RAGFLOW_CONFIG', 'conf/service_conf.yaml'))
        model_cfg = cfg.user_default_llm.default_models.embedding_model
        
        provider = model_cfg.provider
        model_name = model_cfg.name
        api_key = None
        base_url = None

        dataset = Dataset.select().where(Dataset.id == dataset_id).first()
        if dataset and dataset.embd_id:
            # If dataset has a specific embedding model e.g. "openai/text-embedding-3-small"
            embd_id = dataset.embd_id

            if "/" in embd_id:
                factory, name = embd_id.split("/", 1)
                # Keep model_name as the full string for litellm
                model_name = embd_id 
                # If it's a remote model, the provider for EmbeddingEngine should be "litellm"
                provider = "litellm" if factory != "huggingface" else "huggingface"
            else:
                factory = embd_id
                name = embd_id

            tenant_llm = TenantLLM.select().where(
                (TenantLLM.tenant_id == dataset.tenant_id) & 
                (TenantLLM.llm_factory == factory) & 
                (TenantLLM.llm_name == name)
            ).first()

            
            if tenant_llm and tenant_llm.api_key:
                api_key = tenant_llm.api_key
                base_url = tenant_llm.api_base

        return EmbeddingConfig(
            provider=provider,
            model=model_name,
            dimension=model_cfg.dimension,
            batch_size=100,
            api_key=api_key,
            base_url=base_url
        )

    def _get_index_name(self, dataset_id: str) -> str:
        # Multi-tenant isolation: isolate indexes by dataset ID securely.
        # Infinity requires table names without dashes.
        return f"idx_{dataset_id.replace('-', '_')}"

    def index_document(self, document_id: str, dataset_id: str, chunks: List[DocumentChunk]):
        if not chunks:
            return

        index_name = self._get_index_name(dataset_id)
        config = self._get_embedding_config(dataset_id)
        
        # 1. Vector index initialization
        self.vector_store.create_index(index_name, dimensions=config.dimension)
        
        # 2. Idempotent reprocessing (delete old records for the given document_id)
        try:
            self.vector_store.delete(index_name, document_id)
        except Exception as e:
            # Table might be empty or missing previously inserted records, which is acceptable.
            logger.warning(f"Error deleting old vectors for {document_id}: {e}")

        # 3. Embed text content
        engine = EmbeddingEngine(config)
        texts = [c.content for c in chunks]
        
        # Tenacity handles retries inside `embed` for remote APIs if configured.
        embeddings = engine.embed(texts)

        # 4. Assemble VectorRecords preserving order
        records = []
        for chunk, embedding in zip(chunks, embeddings):
            record = VectorRecord(
                id=chunk.id,  # 1:1 mapping with chunk_id for stable identifier
                document_id=document_id,
                dataset_id=dataset_id,
                content=chunk.content,
                embedding=embedding,
                metadata={}
            )
            records.append(record)

        # 5. Bulk insert to vector store
        # Insert operations happen as batches if the vector store adapter supports it
        self.vector_store.bulk_insert(index_name, records)

indexing_service = IndexingService()
