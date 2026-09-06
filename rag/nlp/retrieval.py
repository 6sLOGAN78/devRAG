import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import concurrent.futures

from rag.vector_store.base import BaseVectorStore, SearchResult
from rag.nlp.embedding import EmbeddingEngine, EmbeddingConfig
from rag.nlp.rerank import RerankEngine, RerankConfig

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
    rerank_rank: int = -1
    rerank_score: float = 0.0
    retrieval_method: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

class RetrievalService:
    def __init__(self, vector_store: BaseVectorStore):
        self.vector_store = vector_store
        # We can cache engines at service level to avoid repeatedly loading weights for local models
        self._rerank_engines = {}

    def _get_embedding_config(self, dataset_id: str) -> EmbeddingConfig:
        return EmbeddingConfig(
            provider="huggingface",
            model="all-MiniLM-L6-v2",
            dimension=384
        )
        
    def _get_rerank_config(self, dataset_id: str) -> RerankConfig:
        return RerankConfig(
            provider="huggingface",
            model="cross-encoder/ms-marco-MiniLM-L-6-v2"
        )
        
    def search(
        self,
        dataset_id: str,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        rrf_k: int = 60,
        candidate_multiplier: int = 3,
        rerank_enabled: bool = True
    ) -> List[RetrievedChunk]:
        """
        Executes hybrid retrieval combining dense and lexical search with RRF fusion,
        followed by Cross-Encoder reranking of the top candidates.
        """
        if not query or not query.strip():
            return []
            
        index_name = f"idx_{dataset_id.replace('-', '_')}"
        config = self._get_embedding_config(dataset_id)
        
        # Candidate pool size bounds the expensive reranking step
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

        # Concurrently fetch dense and lexical candidate sets
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_dense = executor.submit(run_dense)
            future_lexical = executor.submit(run_lexical)
            
            # Dense is required; let exception bubble up
            dense_results = future_dense.result()
            lexical_results = future_lexical.result()
        
        # Merge candidates and apply RRF
        fused = self._fuse_results(dense_results, lexical_results, rrf_k, candidate_k)
        
        if not fused:
            return []
            
        # Optional Cross-Encoder Reranking Phase
        if rerank_enabled:
            rerank_config = self._get_rerank_config(dataset_id)
            if rerank_config.model not in self._rerank_engines:
                self._rerank_engines[rerank_config.model] = RerankEngine(rerank_config)
                
            engine = self._rerank_engines[rerank_config.model]
            
            try:
                texts = [c.content for c in fused]
                scores = engine.rerank_scores(query, texts)
                
                if len(scores) != len(fused):
                    raise ValueError(f"Reranker returned {len(scores)} scores for {len(fused)} chunks")
                    
                for i, chunk in enumerate(fused):
                    chunk.rerank_score = float(scores[i])
                    
                # Deterministic Re-sort: Rerank Score > Original Fused Score > Chunk ID
                fused.sort(key=lambda x: (
                    -x.rerank_score,
                    -x.score,
                    x.chunk_id
                ))
                
                # Assign rerank ranks
                for rank, chunk in enumerate(fused):
                    chunk.rerank_rank = rank + 1
                    
            except Exception as e:
                logger.error(f"Reranking failed: {e}. Falling back to Hybrid Fusion ranking.")
                # Fallback implicitly leaves the array sorted by RRF since we haven't re-sorted yet
                
        return fused[:top_k]

    def _fuse_results(
        self, 
        dense_results: List[SearchResult], 
        lexical_results: List[SearchResult], 
        rrf_k: int, 
        top_k: int
    ) -> List[RetrievedChunk]:
        
        chunk_map: Dict[str, RetrievedChunk] = {}
        
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
            chunk_map[res.id].score += 1.0 / (rrf_k + chunk_map[res.id].dense_rank)
            
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
            chunk.score += 1.0 / (rrf_k + chunk.lexical_rank)
            
        fused = list(chunk_map.values())
        
        fused.sort(key=lambda x: (
            -x.score,
            x.lexical_rank if x.lexical_rank > 0 else 999999,
            x.dense_rank if x.dense_rank > 0 else 999999,
            x.chunk_id
        ))
        
        return fused[:top_k]
