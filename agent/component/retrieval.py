import logging
from typing import Any, Dict, Optional, List
from jinja2.sandbox import SandboxedEnvironment
from jinja2 import StrictUndefined, TemplateError

from .base import AgentNode
from rag.nlp.retrieval import RetrievalService
from rag.vector_store.infinity_adapter import InfinityAdapter

logger = logging.getLogger(__name__)

# Cache service globally to avoid recreating connections and model weights on every node execution.
_retrieval_service_instance = None

def get_retrieval_service() -> RetrievalService:
    global _retrieval_service_instance
    if _retrieval_service_instance is None:
        vector_store = InfinityAdapter()
        _retrieval_service_instance = RetrievalService(vector_store)
    return _retrieval_service_instance

class RetrievalNode(AgentNode):
    """
    Executes RAG retrieval using Phase 06 HybridRetrievalService.
    Produces a context string suitable for LLM injection.
    """
    def __init__(self, node_id: str, config: Optional[Dict[str, Any]] = None):
        super().__init__(node_id, config)
        self.dataset_id = self.config.get("dataset_id")
        self.query_template = self.config.get("query", "")
        self.top_k = self.config.get("top_k", 5)
        self.threshold = self.config.get("threshold", 0.0)
        
        self._jinja_env = SandboxedEnvironment(undefined=StrictUndefined)
        
    def _render_template(self, template_str: str, resolved_inputs: Dict[str, Any]) -> str:
        if not template_str:
            return ""
        try:
            template = self._jinja_env.from_string(template_str)
            return template.render(**resolved_inputs)
        except TemplateError as e:
            raise ValueError(f"Template rendering failed in node {self.id}: {str(e)}")

    def execute(self, resolved_inputs: Dict[str, Any]) -> Dict[str, Any]:
        if not self.dataset_id:
            raise ValueError(f"RetrievalNode {self.id} requires a dataset_id")
            
        print(f"DEBUG resolved_inputs: {resolved_inputs}")
        dataset_id = self._render_template(self.dataset_id, resolved_inputs) if "{{" in self.dataset_id else self.dataset_id
        
        with open("debug_inputs.txt", "w") as f: f.write(str(resolved_inputs))
        # TENANT ISOLATION CHECK
        tenant_id = resolved_inputs.get("__tenant_id__")
        if tenant_id:
            from api.db.db_models import Dataset
            dataset = Dataset.get_or_none((Dataset.id == dataset_id) & (Dataset.tenant_id == tenant_id))
            if not dataset:
                raise ValueError(f"Security Error: Dataset {dataset_id} not found or access denied for tenant {tenant_id}")

            
        query = self._render_template(self.query_template, resolved_inputs)
        if not query or not query.strip():
            raise ValueError(f"RetrievalNode {self.id} resolved an empty query")
            
        retrieval_service = get_retrieval_service()
        
        try:
            results = retrieval_service.search(
                dataset_id=dataset_id,
                query=query.strip(),
                top_k=self.top_k,
                rerank_enabled=True
            )
        except Exception as e:
            logger.error(f"Retrieval service failed in node {self.id}: {e}")
            raise RuntimeError(f"Retrieval operation failed: {str(e)}")
            
        if self.threshold > 0:
            # Determine threshold filtering (we use rerank_score as priority if rerank is enabled, else raw score)
            results = [r for r in results if max(r.score, getattr(r, 'rerank_score', 0.0)) >= self.threshold]
            
        context_parts = []
        chunks_data = []
        
        for i, chunk in enumerate(results):
            source = chunk.metadata.get("source", chunk.document_id)
            context_parts.append(f"--- CHUNK {i+1} ---\n[Source: {source}]\n{chunk.content}")
            
            chunk_info = {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "score": chunk.score,
                "rerank_score": getattr(chunk, 'rerank_score', 0.0),
                "content": chunk.content,
                "source": source
            }
            if "page" in chunk.metadata:
                chunk_info["page"] = chunk.metadata["page"]
            if "bbox" in chunk.metadata:
                chunk_info["bbox"] = chunk.metadata["bbox"]
                
            chunks_data.append(chunk_info)
            
        context_string = "\n\n".join(context_parts)
        
        return {
            "context": context_string,
            "chunks": chunks_data
        }
