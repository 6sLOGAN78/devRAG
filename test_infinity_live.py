import os
import uuid
import logging
from api.db.db_models import DocumentChunk
from api.services.indexing_service import indexing_service

logging.basicConfig(level=logging.INFO)

doc_id = str(uuid.uuid4())
dataset_id = "test-dataset-123"
chunks = [
    DocumentChunk(id=str(uuid.uuid4()), document_id=doc_id, content="This is a test chunk.")
]

try:
    print("Testing live indexing against Infinity...")
    indexing_service.index_document(doc_id, dataset_id, chunks)
    print("Indexing succeeded!")
    
    # Verify search
    vector_store = indexing_service.vector_store
    config = indexing_service._get_embedding_config(dataset_id)
    from rag.nlp.embedding import EmbeddingEngine
    query_vector = EmbeddingEngine(config).embed(["test chunk"])[0]
    
    results = vector_store.search(f"idx_{dataset_id.replace('-','_')}", query_vector, top_k=1)
    print(f"Search found {len(results)} results.")
    for r in results:
        print(f"  -> {r.content} (score={r.score})")
        
except Exception as e:
    print(f"Integration failed: {e}")
