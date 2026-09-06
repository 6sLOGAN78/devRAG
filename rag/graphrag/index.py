import logging
from common.redis_conn import RedisDistributedLock

logger = logging.getLogger(__name__)

class GraphRAGIndexer:
    def __init__(self, kb_id: str):
        self.kb_id = kb_id

    def build_index(self, documents: list):
        """
        Builds the GraphRAG index.
        The mutation of the knowledge base graph state is protected by a distributed lock
        to avoid race conditions between concurrent indexing jobs for the same KB.
        """
        lock_name = f"graphrag_task_{self.kb_id}"
        logger.info(f"Preparing to build GraphRAG index for KB {self.kb_id}...")
        
        # 1. Non-critical work (e.g., extracting entities via LLM) can happen outside the lock
        extracted_data = self._extract_entities(documents)
        
        # 2. Critical section: merging into the shared graph state
        try:
            with RedisDistributedLock(lock_name, timeout=300, blocking_timeout=60) as lock:
                logger.info(f"Acquired lock {lock_name}. Merging graph state...")
                self._merge_graph_state(extracted_data)
                logger.info(f"Successfully merged graph state for KB {self.kb_id}.")
        except TimeoutError:
            logger.error(f"Failed to acquire GraphRAG lock {lock_name} within timeout.")
            raise

    def _extract_entities(self, documents: list):
        # Stub for expensive LLM entity extraction
        return {"nodes": [], "edges": []}

    def _merge_graph_state(self, graph_data: dict):
        # Stub for mutating the persistent graph structure
        pass
