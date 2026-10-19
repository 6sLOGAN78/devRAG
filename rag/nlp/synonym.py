"""Synonym source: a small in-repo dictionary with a per-term Valkey cache (RETR-04 Partial, ING-21 Partial; R-203).

A term is looked up under the key ``synonym_{term}`` (a JSON list). On a miss the dictionary in ``rag/res/synonym.json``
answers and the answer, empty or not, is written back with ``retrieval.synonym_ttl_seconds``. The cache fails open: any
Valkey or network error answers from the dictionary and ends cache use for the rest of the batch. The client is created per
batch with a 2 s socket timeout and closed in ``finally`` (the pattern of ``common/ratelimit.py``). Logs carry exception
class names only, never a term.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import valkey
from valkey.exceptions import ValkeyError

from common.settings import RedisSettings, RetrievalSettings

logger = logging.getLogger(__name__)

SOCKET_TIMEOUT_SECONDS = 2
MAX_SYNONYMS = 3
MAX_TERM_CHARS = 64
KEY_PREFIX = "synonym_"
DICTIONARY_PATH = Path(__file__).resolve().parent.parent / "res" / "synonym.json"


@lru_cache(maxsize=1)
def load_dictionary() -> dict[str, tuple[str, ...]]:
    """Load the dictionary once per process and make it symmetric (``invoice`` -> ``bill`` implies ``bill`` -> ``invoice``)."""
    raw = json.loads(DICTIONARY_PATH.read_text(encoding="utf-8"))
    merged: dict[str, list[str]] = {}
    for term, others in raw.items():
        for left, right in ((term, others), *((o, [term]) for o in others)):
            bucket = merged.setdefault(left.lower(), [])
            for word in right:
                word = word.lower()
                if word != left.lower() and word not in bucket:
                    bucket.append(word)
    return {term: tuple(words[:MAX_SYNONYMS]) for term, words in merged.items()}


def _cacheable(term: str) -> bool:
    return 0 < len(term) <= MAX_TERM_CHARS and not any(c.isspace() for c in term)


class SynonymSource:
    def __init__(
        self,
        redis: RedisSettings | None,
        retrieval: RetrievalSettings,
        *,
        client_factory: Callable[[], valkey.Valkey] | None = None,
    ) -> None:
        self._redis = redis
        self._ttl = retrieval.synonym_ttl_seconds
        self._factory = client_factory

    def _client(self) -> valkey.Valkey | None:
        if self._factory is not None:
            return self._factory()
        rd = self._redis
        if rd is None:
            return None
        return valkey.Valkey(
            host=rd.host,
            port=rd.port,
            password=rd.password or None,
            db=rd.db,
            socket_timeout=SOCKET_TIMEOUT_SECONDS,
            socket_connect_timeout=SOCKET_TIMEOUT_SECONDS,
        )

    def lookup(self, term: str) -> list[str]:
        return self.lookup_many([term])[term]

    def lookup_many(self, terms: list[str]) -> dict[str, list[str]]:
        """Answer every term; one client serves the batch and the first cache failure ends cache use for it."""
        dictionary = load_dictionary()
        out: dict[str, list[str]] = {}
        client = None
        use_cache = any(_cacheable(t) for t in terms)
        try:
            if use_cache:
                try:
                    client = self._client()
                except (ValkeyError, OSError) as exc:
                    self._log_outage(exc)
                use_cache = client is not None
            for term in terms:
                out[term], failed = self._one(term, dictionary, client if use_cache else None)
                use_cache = use_cache and not failed
        finally:
            if client is not None:
                try:
                    client.close()
                except (ValkeyError, OSError):
                    pass
        return out

    def _one(self, term: str, dictionary: dict[str, tuple[str, ...]], client: valkey.Valkey | None) -> tuple[list[str], bool]:
        """Return the answer and whether the cache failed (the dictionary answers either way)."""
        local = list(dictionary.get(term.lower(), ()))[:MAX_SYNONYMS]
        if client is None or not _cacheable(term):
            return local, False
        key = KEY_PREFIX + term
        try:
            hit = _decode(client.get(key))
            if hit is not None:
                return hit, False
            client.setex(key, self._ttl, json.dumps(local))
        except (ValkeyError, OSError) as exc:
            self._log_outage(exc)
            return local, True
        return local, False

    @staticmethod
    def _log_outage(exc: Exception) -> None:
        logger.warning("synonym cache unavailable: %s", type(exc).__name__)


def _decode(raw: object) -> list[str] | None:
    if raw is None:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        return None
    return value[:MAX_SYNONYMS]
