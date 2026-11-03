"""RAPTOR must build real, bounded hierarchy and retain original leaf provenance."""
import pytest

from rag.svr import dataset_jobs
from rag.advanced_rag.raptor import Leaf, RaptorError, build_hierarchy, cluster_vectors

pytestmark = pytest.mark.unit


def test_raptor_worker_has_a_distinct_job_path():
    # First RED: the enrichment-only worker cannot process a RAPTOR job.
    assert callable(getattr(dataset_jobs, "run_raptor", None))


def test_small_corpus_clustering_is_deterministic_and_bounded():
    vectors = [[1.0, 0.0], [0.99, 0.01], [0.0, 1.0], [0.01, 0.99],
               [-1.0, 0.0], [-0.99, 0.01], [0.0, -1.0], [0.01, -0.99]]
    first = cluster_vectors(vectors, seed=42)
    assert first == cluster_vectors(vectors, seed=42)
    assert 2 <= len(first) <= 4
    assert sorted(i for group in first for i in group) == list(range(len(vectors)))
    assert all(2 <= len(group) <= 4 for group in first)


def test_hierarchy_has_three_real_levels_and_stable_source_ids():
    leaves = [Leaf(f"leaf-{i}", "a" * 32, f"Source fact {i}", (float(i + 1), float(8 - i))) for i in range(8)]
    calls = []
    def summarize(texts, level):
        calls.append((level, tuple(texts)))
        return f"Level {level}: interpreted {len(texts)} source passages"
    made = build_hierarchy(leaves, "a" * 64, summarize, lambda texts: [[float(i + 1), 1.0] for i in range(len(texts))])
    assert [sum(row.level == level for row in made) for level in (1, 2, 3)] == [4, 2, 1]
    assert set(made[-1].leaf_ids) == {leaf.chunk_id for leaf in leaves}
    assert all(row.text not in {leaf.text for leaf in leaves} for row in made)
    assert all(len(row.child_ids) >= 2 for row in made)
    assert len(calls) == 7


def test_large_corpus_requires_native_clusterer_and_rejects_missing_sources():
    vectors = [[float(i + 1), 1.0] for i in range(9)]
    with pytest.raises(RaptorError, match="native"):
        cluster_vectors(vectors)
    with pytest.raises(RaptorError, match="lost or duplicated"):
        cluster_vectors(vectors, native=lambda _rows, _seed: [[0, 1], [2, 3]])


def test_oversized_summary_and_context_fail_before_embedding():
    leaves = [Leaf("a", "doc", "source one", (1.0, 0.0)), Leaf("b", "doc", "source two", (0.0, 1.0))]
    with pytest.raises(RaptorError, match="invalid text"):
        build_hierarchy(leaves, "a" * 64, lambda _texts, _level: "x" * 2001,
                        lambda _texts: pytest.fail("an oversized summary was embedded"))
    huge = [Leaf("a", "doc", "x" * 7000, (1.0, 0.0)), Leaf("b", "doc", "y" * 7000, (0.0, 1.0))]
    with pytest.raises(RaptorError, match="context"):
        build_hierarchy(huge, "a" * 64, lambda _texts, _level: pytest.fail("an oversized context reached the model"),
                        lambda _texts: pytest.fail("an oversized context was embedded"))


def test_saved_summary_reference_rechecks_leaves_and_redacts_stale_text(monkeypatch):
    from api.db.services import conversation_redaction as redaction
    from api.db.services import raptor_visibility

    message = {"role": "assistant", "content": "saved answer", "reference": {"chunks": [
        {"index": 0, "chunk_id": "summary", "doc_id": "doc", "dataset_id": "dataset",
         "summary_level": 1, "content": "derived secret", "source_leaves": [{"content": "old passage"}]}
    ]}}
    monkeypatch.setattr(redaction, "live_datasets", lambda _ids: {"dataset": object()})
    monkeypatch.setattr(redaction, "openable", lambda *_args: True)
    monkeypatch.setattr(raptor_visibility, "current_reference_summaries", lambda _rows, _tenant: {
        "summary": [{"chunk_id": "leaf", "doc_id": "doc", "dataset_id": "dataset", "content": "current passage"}]
    })
    fresh = redaction.redact_messages([message], "tenant", "user")[0]["reference"]["chunks"][0]
    assert fresh["content"] == "derived secret"
    assert fresh["source_leaves"] == [{"chunk_id": "leaf", "doc_id": "doc", "dataset_id": "dataset", "content": "current passage"}]
    monkeypatch.setattr(raptor_visibility, "current_reference_summaries", lambda _rows, _tenant: {})
    stale = redaction.redact_messages([message], "tenant", "user")[0]["reference"]["chunks"]
    assert stale == [{"index": 0, "unavailable": True}]
