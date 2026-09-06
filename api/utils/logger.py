import logging
import json
import uuid
from quart import request, g

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname.lower(),
            "service": "python_api",
            "message": record.getMessage(),
        }
        if hasattr(g, 'request_id'):
            log_record['request_id'] = g.request_id
        if hasattr(g, 'user_id'):
            log_record['user_id'] = g.user_id
        if hasattr(g, 'tenant_id'):
            log_record['tenant_id'] = g.tenant_id
            
        if record.exc_info:
            log_record['exc_info'] = self.formatException(record.exc_info)
            
        # Extract extra attrs
        if hasattr(record, 'event'):
            log_record['event'] = record.event
            
        return json.dumps(log_record)

def setup_logger():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Remove all handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(JSONFormatter())
    logger.addHandler(ch)
