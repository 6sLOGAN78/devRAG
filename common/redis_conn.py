import redis
import time
import uuid
import logging
from common.settings import load_config

logger = logging.getLogger(__name__)

class RedisConnection:
    _client = None

    @classmethod
    def get_client(cls):
        if cls._client is None:
            cfg = load_config('conf/service_conf.yaml')
            cls._client = redis.Redis(
                host=cfg.redis.host,
                port=cfg.redis.port,
                db=cfg.redis.db,
                decode_responses=True
            )
        return cls._client

class RedisDistributedLock:
    def __init__(self, lock_name: str, timeout: int = 60, blocking: bool = True, blocking_timeout: int = 10):
        self.client = RedisConnection.get_client()
        self.lock_name = f"devrag:lock:{lock_name}"
        self.timeout = timeout
        self.blocking = blocking
        self.blocking_timeout = blocking_timeout
        self.token = str(uuid.uuid4())
        self._acquired = False

    def acquire(self) -> bool:
        start_time = time.time()
        while True:
            acquired = self.client.set(self.lock_name, self.token, nx=True, ex=self.timeout)
            if acquired:
                self._acquired = True
                return True

            if not self.blocking:
                return False

            if time.time() - start_time > self.blocking_timeout:
                logger.warning(f"Timeout while waiting to acquire lock: {self.lock_name}")
                return False

            time.sleep(0.1)

    def release(self):
        if not self._acquired:
            return

        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        try:
            self.client.eval(lua_script, 1, self.lock_name, self.token)
        except Exception as e:
            logger.error(f"Error releasing lock {self.lock_name}: {e}")
        finally:
            self._acquired = False

    def __enter__(self):
        if not self.acquire():
            raise TimeoutError(f"Unable to acquire Redis lock for {self.lock_name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
