"""Cached queue factory (plan 04-07). The Valkey Streams class is the only implementation (D-18)."""
from __future__ import annotations

import threading

from common.settings import Settings
from rag.queue.queue_base import TaskQueue
from rag.queue.valkey_streams import ValkeyStreamQueue

_LOCK = threading.Lock()
_CACHE: dict[tuple[str, int, int, str, str], TaskQueue] = {}


def get_queue(settings: Settings) -> TaskQueue:
    rd, ing = settings.redis, settings.ingest
    key = (rd.host, rd.port, rd.db, ing.queue_prefix, ing.consumer_group)
    with _LOCK:
        cached = _CACHE.get(key)
        if cached is None:
            cached = _CACHE[key] = ValkeyStreamQueue(settings)
        return cached


def reset_queue_cache() -> None:
    with _LOCK:
        for queue in _CACHE.values():
            queue.close()
        _CACHE.clear()
