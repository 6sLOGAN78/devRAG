import asyncio
import logging
from datetime import datetime, timedelta
from api.db.db_models import DocumentTask, Document
from common.redis_conn import RedisDistributedLock

logger = logging.getLogger(__name__)

async def clean_task_executor_loop():
    """
    Background thread to clean up stale 'running' tasks that have crashed or timed out.
    """
    while True:
        try:
            # We use a distributed lock so only one worker performs cleanup
            with RedisDistributedLock("clean_task_executor", timeout=30, blocking=False):
                # Any task stuck in 'running' for more than 30 minutes is considered stale/dead
                cutoff_time = datetime.now() - timedelta(minutes=30)
                
                stale_tasks = DocumentTask.select().where(
                    (DocumentTask.status == 'running') &
                    (DocumentTask.updated_at < cutoff_time)
                )
                
                for task in stale_tasks:
                    logger.warning(f"Cleaning up stale task {task.id}")
                    task.status = 'failed'
                    task.error_msg = "Task timed out during execution."
                    task.updated_at = datetime.now()
                    task.save()
                    
                    doc = Document.get_or_none(Document.id == task.document_id)
                    if doc:
                        doc.parse_status = 'failed'
                        doc.save()
                        
        except Exception as e:
            # If we fail to acquire the lock (because another instance is cleaning) or hit an error, skip
            if not isinstance(e, TimeoutError):
                logger.error(f"Error in task executor cleaner: {e}")
                
        await asyncio.sleep(60 * 5) # run every 5 minutes
