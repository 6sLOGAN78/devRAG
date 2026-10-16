"""Named bounded limiters for blocking work (ING-09, ING-13, ING-14, D-05).

``kg_limiter`` is built and tested but no stage takes it in this phase; knowledge-graph extraction is a later phase.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from common.settings import IngestSettings


@dataclass(frozen=True)
class Limiters:
    task_limiter: threading.BoundedSemaphore
    chunk_limiter: threading.BoundedSemaphore
    embed_limiter: threading.BoundedSemaphore
    minio_limiter: threading.BoundedSemaphore
    kg_limiter: threading.BoundedSemaphore

    @classmethod
    def from_settings(cls, ingest: IngestSettings) -> Limiters:
        return cls(
            task_limiter=threading.BoundedSemaphore(ingest.task_concurrency),
            chunk_limiter=threading.BoundedSemaphore(ingest.chunk_concurrency),
            embed_limiter=threading.BoundedSemaphore(ingest.embed_concurrency),
            minio_limiter=threading.BoundedSemaphore(ingest.storage_concurrency),
            kg_limiter=threading.BoundedSemaphore(ingest.kg_concurrency),
        )
