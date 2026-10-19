"""Synonym source: in-repo dictionary plus a Valkey cache that fails open (RETR-04 Partial, ING-21 Partial; R-203)."""

from __future__ import annotations

import json

import pytest

from common.settings import RedisSettings, RetrievalSettings
from rag.nlp.synonym import SynonymSource, load_dictionary

pytestmark = pytest.mark.unit

REDIS = RedisSettings(host="valkey.invalid", port=6379, password="x", db=0)


class FakeClient:
    def __init__(self, store: dict[str, str] | None = None) -> None:
        self.store = store if store is not None else {}
        self.gets: list[str] = []
        self.setex_calls: list[tuple[str, int, str]] = []
        self.closed = False

    def get(self, key: str) -> str | None:
        self.gets.append(key)
        return self.store.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.setex_calls.append((key, ttl, value))
        self.store[key] = value

    def close(self) -> None:
        self.closed = True


def _source(client: FakeClient, ttl: int = 777) -> SynonymSource:
    return SynonymSource(REDIS, RetrievalSettings(synonym_ttl_seconds=ttl), client_factory=lambda: client)


def test_dictionary_ships_with_at_least_thirty_entries_and_is_symmetric() -> None:
    d = load_dictionary()
    assert len(d) >= 30
    assert "bill" in d["invoice"] and "invoice" in d["bill"]
    assert "agreement" in d["contract"] and "contract" in d["agreement"]


def test_dictionary_hit_on_a_cache_miss_writes_the_cache_with_the_ttl() -> None:
    client = FakeClient()
    out = _source(client, ttl=777).lookup("invoice")
    assert "bill" in out and len(out) <= 3
    assert client.gets == ["synonym_invoice"]
    key, ttl, value = client.setex_calls[0]
    assert (key, ttl) == ("synonym_invoice", 777)
    assert json.loads(value) == out
    assert client.closed


def test_cache_hit_is_returned_without_reading_the_dictionary_or_writing() -> None:
    client = FakeClient({"synonym_invoice": json.dumps(["cached-one"])})
    assert _source(client).lookup("invoice") == ["cached-one"]
    assert client.setex_calls == []


def test_unknown_term_returns_empty_and_caches_empty() -> None:
    client = FakeClient()
    assert _source(client, ttl=120).lookup("zzyzx") == []
    assert client.setex_calls == [("synonym_zzyzx", 120, "[]")]
    # the cached empty list is a hit the second time
    client.setex_calls.clear()
    assert _source(client).lookup("zzyzx") == []
    assert client.setex_calls == []


def test_at_most_three_synonyms_even_from_the_cache() -> None:
    client = FakeClient({"synonym_many": json.dumps(["a1", "b2", "c3", "d4", "e5"])})
    assert _source(client).lookup("many") == ["a1", "b2", "c3"]
    assert len(load_dictionary()["company"]) <= 3


def test_a_corrupt_cache_value_is_a_miss() -> None:
    client = FakeClient({"synonym_invoice": "not json"})
    assert "bill" in _source(client).lookup("invoice")
    client2 = FakeClient({"synonym_invoice": json.dumps({"x": 1})})
    assert "bill" in _source(client2).lookup("invoice")


def test_outage_on_connect_falls_back_to_the_dictionary() -> None:
    def broken() -> FakeClient:
        raise ConnectionError("down")

    source = SynonymSource(REDIS, RetrievalSettings(), client_factory=broken)
    assert "bill" in source.lookup("invoice")
    assert source.lookup("zzyzx") == []


def test_outage_on_a_command_falls_back_and_stops_asking_the_cache() -> None:
    class Flaky(FakeClient):
        def get(self, key: str) -> str | None:
            self.gets.append(key)
            raise OSError("reset")

    client = Flaky()
    out = _source(client).lookup_many(["invoice", "contract", "zzyzx"])
    assert "bill" in out["invoice"] and "agreement" in out["contract"] and out["zzyzx"] == []
    assert len(client.gets) == 1  # the first failure ends cache use for the batch
    assert client.closed


def test_lookup_many_uses_one_client() -> None:
    made: list[FakeClient] = []

    def factory() -> FakeClient:
        made.append(FakeClient())
        return made[-1]

    source = SynonymSource(REDIS, RetrievalSettings(), client_factory=factory)
    out = source.lookup_many(["invoice", "contract"])
    assert set(out) == {"invoice", "contract"}
    assert len(made) == 1


def test_oversized_or_odd_terms_skip_the_cache() -> None:
    client = FakeClient()
    source = _source(client)
    assert source.lookup("x" * 200) == []
    assert source.lookup("has space") == []
    assert client.gets == []
