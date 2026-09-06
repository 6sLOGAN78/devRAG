import abc
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class VectorRecord(BaseModel):
    id: str
    document_id: str
    dataset_id: str
    content: str
    embedding: List[float]
    metadata: Dict[str, Any] = {}

class SearchResult(BaseModel):
    id: str
    document_id: str
    dataset_id: str
    content: str
    score: float
    metadata: Dict[str, Any] = {}

class BaseVectorStore(abc.ABC):
    @abc.abstractmethod
    def create_index(self, index_name: str, dimensions: int) -> None:
        """Create a new vector index if it does not exist."""
        pass
    
    @abc.abstractmethod
    def delete_index(self, index_name: str) -> None:
        """Delete an existing vector index."""
        pass
        
    @abc.abstractmethod
    def bulk_insert(self, index_name: str, records: List[VectorRecord]) -> None:
        """Insert a batch of vector records."""
        pass
        
    @abc.abstractmethod
    def search(
        self, 
        index_name: str, 
        query_vector: List[float], 
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """Search the index for similar vectors."""
        pass
        
    @abc.abstractmethod
    def delete(self, index_name: str, document_id: str) -> None:
        """Delete all vectors associated with a specific document."""
        pass
        
    @abc.abstractmethod
    def health_check(self) -> bool:
        """Check if the vector store is reachable and healthy."""
        pass
