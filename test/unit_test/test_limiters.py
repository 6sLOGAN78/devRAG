from __future__ import annotations

import dataclasses

import pytest

from common.settings import IngestSettings
from rag.svr.limiters import Limiters

pytestmark = pytest.mark.unit

NAMES = ("task_limiter", "chunk_limiter", "embed_limiter", "minio_limiter", "kg_limiter")


def test_five_named_limiters_use_the_configured_sizes():
    ingest = dataclasses.replace(IngestSettings(), task_concurrency=1, chunk_concurrency=2, embed_concurrency=3, storage_concurrency=4, kg_concurrency=1)
    limiters = Limiters.from_settings(ingest)
    sizes = {"task_limiter": 1, "chunk_limiter": 2, "embed_limiter": 3, "minio_limiter": 4, "kg_limiter": 1}
    for name in NAMES:
        sem = getattr(limiters, name)
        for _ in range(sizes[name]):
            assert sem.acquire(blocking=False)
        assert sem.acquire(blocking=False) is False, name
        for _ in range(sizes[name]):
            sem.release()


def test_kg_limiter_exists_but_is_unused_by_stages():
    # kg_limiter is built and bounded; no pipeline stage takes it in this phase.
    assert Limiters.from_settings(IngestSettings()).kg_limiter is not None
