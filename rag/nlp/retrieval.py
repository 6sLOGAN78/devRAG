import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import concurrent.futures

from rag.vector_store.base import BaseVectorStore, SearchResult
from rag.nlp.embedding import EmbeddingEngine, EmbeddingConfig

logger = logging.getLogger(__name__)

@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    dataset_id: str
    content: str
    score: float
    dense_rank: int = -1
    lexical_rank: int = -1
    dense_score: float = 0.0
    lexical_score: float = 0.0
    retrieval_method: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

class RetrievalService:
    def __init__(self, vector_store: BaseVectorStore):
        self.vector_store = vector_store

    def _get_embedding_config(self, dataset_id: str) -> EmbeddingConfig:
        # Resolves dataset embedding configuration.
        # Fallback aligns with 06-03 architecture assumptions.
        return EmbeddingConfig(
            provider="huggingface",
            model="all-MiniLM-L6-v2",
            dimension=384
        )
        
    def search(
        self,
        dataset_id: str,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        rrf_k: int = 60,
        candidate_multiplier: int = 3
    ) -> List[RetrievedChunk]:
        """
        Executes hybrid retrieval combining dense and lexical search with RRF fusion.
        """
        if not query or not query.strip():
            return []
            
        index_name = f"idx_{dataset_id.replace('-', '_')}"
        config = self._get_embedding_config(dataset_id)
        
        # Fetch more candidates than top_k for better fusion coverage
        candidate_k = top_k * candidate_multiplier
        
        dense_results: List[SearchResult] = []
        lexical_results: List[SearchResult] = []
        
        def run_dense() -> List[SearchResult]:
            try:
                engine = EmbeddingEngine(config)
                query_vector = engine.embed([query])[0]
                return self.vector_store.search(
                    index_name, query_vector, top_k=candidate_k, filters=filters
                )
            except Exception as e:
                logger.error(f"Dense search failed: {e}")
                raise e
                
        def run_lexical() -> List[SearchResult]:
            try:
                return self.vector_store.search_lexical(
                    index_name, query, top_k=candidate_k, filters=filters
                )
            except Exception as e:
                logger.warning(f"Lexical search failed or unsupported: {e}. Falling back to dense only.")
                return []

        # Run concurrently to minimize latency (lexical doesn't wait for embedding generation)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_dense = executor.submit(run_dense)
            future_lexical = executor.submit(run_lexical)
            
            # Dense is strictly required. If it fails, bubble up the error.
            dense_results = future_dense.result()
            
            # Lexical is optional and may gracefully degrade if the backend lacks FTS
            lexical_results = future_lexical.result()
        
        return self._fuse_results(dense_results, lexical_results, rrf_k, top_k)

    def _fuse_results(
        self, 
        dense_results: List[SearchResult], 
        lexical_results: List[SearchResult], 
        rrf_k: int, 
        top_k: int
    ) -> List[RetrievedChunk]:
        
        chunk_map: Dict[str, RetrievedChunk] = {}
        
        # 1. Process Dense Results
        for rank, res in enumerate(dense_results):
            chunk_map[res.id] = RetrievedChunk(
                chunk_id=res.id,
                document_id=res.document_id,
                dataset_id=res.dataset_id,
                content=res.content,
                score=0.0,
                dense_rank=rank + 1,
                dense_score=res.score,
                retrieval_method="dense",
                metadata=res.metadata or {}
            )
            # Add RRF score contribution
            chunk_map[res.id].score += 1.0 / (rrf_k + chunk_map[res.id].dense_rank)
            
        # 2. Process Lexical Results
        for rank, res in enumerate(lexical_results):
            if res.id not in chunk_map:
                chunk_map[res.id] = RetrievedChunk(
                    chunk_id=res.id,
                    document_id=res.document_id,
                    dataset_id=res.dataset_id,
                    content=res.content,
                    score=0.0,
                    metadata=res.metadata or {}
                )
                chunk_map[res.id].retrieval_method = "lexical"
            else:
                chunk_map[res.id].retrieval_method = "hybrid"
                
            chunk = chunk_map[res.id]
            chunk.lexical_rank = rank + 1
            chunk.lexical_score = res.score
            # Add RRF score contribution
            chunk.score += 1.0 / (rrf_k + chunk.lexical_rank)
            
        fused = list(chunk_map.values())
        
        # 3. Deterministic Tie-breaking
        # primary: RRF score descending
        # secondary: lexical rank ascending (lower is better, absent=999999)
        # tertiary: dense rank ascending
        # quaternary: chunk_id (stable identifier)
        fused.sort(key=lambda x: (
            -x.score,
            x.lexical_rank if x.lexical_rank > 0 else 999999,
            x.dense_rank if x.dense_rank > 0 else 999999,
            x.chunk_id
        ))
        
        return fused[:top_k]
