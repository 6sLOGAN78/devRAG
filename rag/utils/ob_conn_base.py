import logging
from common.redis_conn import RedisDistributedLock

logger = logging.getLogger(__name__)

class DocumentStoreBase:
    def __init__(self, kb_id: str):
        self.kb_id = kb_id
        # We assume lock_name conventionally includes kb_id for the document store scope
        self.lock_name = f"doc_store_{self.kb_id}"
        
    def initialize(self):
        """Initialize the document store using distributed locks to prevent race conditions."""
        try:
            with RedisDistributedLock(self.lock_name, timeout=60, blocking_timeout=30) as lock:
                logger.info(f"Initialized document store for {self.kb_id} safely.")
                # Critical section for initializing indices or tracking structures
                self._do_initialize()
        except TimeoutError:
            logger.error(f"Failed to acquire lock {self.lock_name} for initialization")
            raise
            
    def write(self, data):
        """Write to the document store safely."""
        try:
            with RedisDistributedLock(self.lock_name, timeout=60, blocking_timeout=30) as lock:
                logger.info(f"Writing to document store for {self.kb_id} safely.")
                # Critical section for concurrent writes
                self._do_write(data)
        except TimeoutError:
            logger.error(f"Failed to acquire lock {self.lock_name} for writing")
            raise
            
    def _do_initialize(self):
        # Actual implementation will go here
        pass
        
    def _do_write(self, data):
        # Actual implementation will go here
        pass
