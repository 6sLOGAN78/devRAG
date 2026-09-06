import pytest
import uuid
import json
import os
from peewee import SqliteDatabase
from api.db.db_models import Document, DocumentChunk, UserTenant, Dataset, db
from agent.component.retrieval import RetrievalNode
from rag.nlp.retrieval import RetrievalService
from rag.nlp.embedding import EmbeddingEngine, EmbeddingConfig
from unittest.mock import patch, MagicMock

test_db = SqliteDatabase(':memory:')

@pytest.fixture(autouse=True)
def setup_database():
    with test_db.bind_ctx([Document, DocumentChunk, UserTenant, Dataset]):
        test_db.create_tables([Document, DocumentChunk, UserTenant, Dataset], safe=True)
        yield
        test_db.drop_tables([Document, DocumentChunk, UserTenant, Dataset], safe=True)

@pytest.mark.asyncio
async def test_full_ingestion_and_retrieval():
    # 1. Setup Tenant & Document
    tenant_id = "tenant_" + str(uuid.uuid4())
    UserTenant.create(user_id="user1", tenant_id=tenant_id, role="admin")
    
    doc_id = str(uuid.uuid4())
    ds = Dataset.create(id="ds1", tenant_id=tenant_id, name="Test DS", created_by="user1")
    doc = Document.create(
        id=doc_id,
        dataset_id="ds1",
        tenant_id=tenant_id,
        name="sample.pdf",
        size="1024",
        type="pdf",
        minio_path="tenant/ds1/sample.pdf",
        parse_status="completed",
        created_by="user1"
    )
    
    chunks_data = [
        {"id": str(uuid.uuid4()), "text": "Integration Test Document", "page": 1, "bbox": [100, 750, 300, 760]},
        {"id": str(uuid.uuid4()), "text": "This is a test paragraph for the ingestion pipeline.", "page": 1, "bbox": [100, 700, 400, 710]}
    ]
    
    for i, c in enumerate(chunks_data):
        DocumentChunk.create(
            id=c["id"],
            document_id=doc.id,
            tenant_id=tenant_id,
            content=c["text"],
            page=c["page"],
            bbox=json.dumps(c["bbox"]),
            chunk_index=i
        )
        
    saved_chunks = list(DocumentChunk.select().where(DocumentChunk.document_id == doc.id))
    assert len(saved_chunks) == 2
    
    # 3. Simulate Embedding & Vector Indexing
    engine = EmbeddingEngine(EmbeddingConfig(provider="huggingface", model="all-MiniLM-L6-v2", dimension=384))
    
    # 4. Retrieval Service Integration
    mock_vs = MagicMock()
    mock_vs.search.return_value = [
        MagicMock(id=chunks_data[1]["id"], document_id=doc.id, dataset_id="ds1", content=chunks_data[1]["text"], score=0.85, metadata={"tenant_id": tenant_id})
    ]
    mock_vs.search_lexical.return_value = []
    
    service = RetrievalService(vector_store=mock_vs)
    
    results = service.search("ds1", "ingestion pipeline", top_k=5, rerank_enabled=False)
    
    assert len(results) > 0
    assert results[0].content == chunks_data[1]["text"]
    
    # 5. GraphRunner Integration (Retrieval Node)
    with patch('agent.component.retrieval.get_retrieval_service') as mock_get_svc:
        mock_get_svc.return_value = service
        
        node = RetrievalNode(node_id="retrieval_1", config={"top_k": 5, "dataset_id": "ds1", "query": "{{query}}"})
        output = node.execute({"query": "ingestion pipeline"})
        
        assert "chunks" in output
        assert len(output["chunks"]) > 0
        assert output["chunks"][0]["content"] == chunks_data[1]["text"]
