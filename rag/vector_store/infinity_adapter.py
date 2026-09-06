import logging
from typing import List, Dict, Any, Optional
import infinity
from infinity.index import IndexInfo, IndexType
from infinity.common import ConflictType
from common.settings import load_config
from .base import BaseVectorStore, VectorRecord, SearchResult

logger = logging.getLogger(__name__)

class InfinityAdapter(BaseVectorStore):
    def __init__(self, db_name: str = "default_db"):
        self.db_name = db_name
        self.client = None
        self._db = None
        self._initialize_client()

    def _initialize_client(self):
        try:
            from infinity.common import NetworkAddress
            cfg = load_config('conf/service_conf.yaml')
            # Assuming infinity running on the given host/port
            uri = NetworkAddress(cfg.infinity.host, cfg.infinity.port)
            self.client = infinity.connect(uri)
            # Create database if not exists
            self.client.create_database(self.db_name, ConflictType.Ignore)
            self._db = self.client.get_database(self.db_name)
            logger.info(f"Connected to Infinity at {cfg.infinity.host}:{cfg.infinity.port}, database: {self.db_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Infinity client: {e}")
            raise

    def health_check(self) -> bool:
        try:
            return self.client is not None
        except Exception:
            return False

    def create_index(self, index_name: str, dimensions: int) -> None:
        """
        Creates a table for the index and adds a vector index.
        Schema:
        - id: varchar
        - document_id: varchar
        - dataset_id: varchar
        - content: varchar
        - embedding: vector(float, dimensions)
        """
        try:
            schema = {
                "id": {"type": "varchar"},
                "document_id": {"type": "varchar"},
                "dataset_id": {"type": "varchar"},
                "content": {"type": "varchar"},
                "embedding": {"type": f"vector,{dimensions},float"}
            }
            
            # Create table
            table = self._db.create_table(index_name, schema, ConflictType.Ignore)
            
            # Create vector index (using HNSW with cosine distance)
            index_info = IndexInfo(
                "embedding",
                IndexType.Hnsw,
                {
                    "metric": "cosine",
                    "M": "16",
                    "ef_construction": "200"
                }
            )
            table.create_index("vec_idx", index_info, ConflictType.Ignore)
            
            # Create full-text index for lexical search
            fts_index_info = IndexInfo("content", IndexType.FullText, {})
            table.create_index("fts_idx", fts_index_info, ConflictType.Ignore)
            
            logger.info(f"Index {index_name} created successfully with dimension {dimensions} and full-text support.")
        except Exception as e:
            logger.error(f"Error creating index {index_name}: {e}")
            raise

    def delete_index(self, index_name: str) -> None:
        try:
            self._db.drop_table(index_name, ConflictType.Ignore)
            logger.info(f"Index {index_name} deleted successfully.")
        except Exception as e:
            logger.error(f"Error deleting index {index_name}: {e}")
            raise

    def bulk_insert(self, index_name: str, records: List[VectorRecord]) -> None:
        try:
            table = self._db.get_table(index_name)
            # Convert VectorRecord to dictionary matching schema
            data = []
            for r in records:
                data.append({
                    "id": r.id,
                    "document_id": r.document_id,
                    "dataset_id": r.dataset_id,
                    "content": r.content,
                    "embedding": r.embedding
                })
                
            table.insert(data)
            logger.info(f"Inserted {len(records)} records into {index_name}.")
        except Exception as e:
            logger.error(f"Error bulk inserting into {index_name}: {e}")
            raise

    def search(
        self, 
        index_name: str, 
        query_vector: List[float], 
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        try:
            table = self._db.get_table(index_name)
            
            # Build search query
            # We match the embedding column using cosine distance
            # In Infinity 0.3.0, SCORE() fails with match_dense. We'll add it back when upgrading or fusing.
            q = table.output(["id", "document_id", "dataset_id", "content"])
            
            if filters:
                # Basic string filtering example: "document_id = 'doc1'"
                # We need to construct filter strings for infinity
                filter_strs = []
                for k, v in filters.items():
                    filter_strs.append(f"{k} = '{v}'")
                filter_expr = " and ".join(filter_strs)
                q = q.filter(filter_expr)
                
            # Perform dense match
            # match_dense arguments: vector_column_name, query_vector, vector_type, metric_type, top_k
            q = q.match_dense("embedding", query_vector, "float", "cosine", top_k)
            
            res_df = q.to_pl()
            
            results = []
            for row in res_df.iter_rows(named=True):
                results.append(SearchResult(
                    id=row["id"],
                    document_id=row["document_id"],
                    dataset_id=row["dataset_id"],
                    content=row["content"],
                    score=0.0, # Placeholder until retrieval phase
                    metadata={}
                ))
            return results
        except Exception as e:
            logger.error(f"Error searching in {index_name}: {e}")
            raise

    def search_lexical(
        self,
        index_name: str,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        try:
            table = self._db.get_table(index_name)
            
            # Using _score for match_text is supported natively by Infinity
            q = table.output(["id", "document_id", "dataset_id", "content", "_score"])
            
            if filters:
                filter_strs = []
                for k, v in filters.items():
                    filter_strs.append(f"{k} = '{v}'")
                filter_expr = " and ".join(filter_strs)
                q = q.filter(filter_expr)
                
            q = q.match_text("content", query, top_k, None)
            
            res_df = q.to_pl()
            
            results = []
            for row in res_df.iter_rows(named=True):
                results.append(SearchResult(
                    id=row["id"],
                    document_id=row["document_id"],
                    dataset_id=row["dataset_id"],
                    content=row["content"],
                    score=row["_score"],
                    metadata={}
                ))
            return results
        except Exception as e:
            logger.error(f"Error in lexical search in {index_name}: {e}")
            raise

    def delete(self, index_name: str, document_id: str) -> None:
        try:
            table = self._db.get_table(index_name)
            table.delete(f"document_id = '{document_id}'")
            logger.info(f"Deleted vectors for document {document_id} from {index_name}")
        except Exception as e:
            logger.error(f"Error deleting from {index_name}: {e}")
            raise
