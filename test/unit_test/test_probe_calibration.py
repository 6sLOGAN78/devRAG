"""The pure parts of the one-off retrieval calibration probe (plan 05-06, RETR-14, research A6, Pitfalls 3 and 12).

The probe itself talks to the live stack and the real embedding model, so it is a manual script and is not collected here. What is tested
is the arithmetic that turns measured scores into a decision, and the evidence writer's allow-list (the key can never reach the file).
"""

from __future__ import annotations

import pytest

from scripts.probe import calibrate_retrieval as probe
from scripts.probe.calibrate_retrieval import Sample, decide, render_evidence, summarise

pytestmark = pytest.mark.unit


def sample(kind: str, similarity: float, label: str = "s") -> Sample:
    return Sample(kind=kind, label=label, weight=0.3, term=0.0, vector=similarity, similarity=similarity)


def summary(rel: tuple[float, float, float], irr: tuple[float, float, float]) -> dict[str, dict[str, float]]:
    keys = ("min", "max", "mean")
    return {"relevant": dict(zip(keys, rel, strict=True)), "irrelevant": dict(zip(keys, irr, strict=True))}


def test_summarise_reports_min_max_and_mean_per_group() -> None:
    samples = [sample("relevant", 0.5), sample("relevant", 0.3), sample("irrelevant", 0.1), sample("irrelevant", 0.05), sample("irrelevant", 0.15)]
    out = summarise(samples)
    assert out["relevant"] == {"min": 0.3, "max": 0.5, "mean": pytest.approx(0.4)}
    assert out["irrelevant"] == {"min": 0.05, "max": 0.15, "mean": pytest.approx(0.1)}


def test_summarise_ignores_other_kinds_and_refuses_an_empty_group() -> None:
    with pytest.raises(ValueError, match="irrelevant"):
        summarise([sample("relevant", 0.4), sample("supplementary", 0.9)])
    with pytest.raises(ValueError, match="relevant"):
        summarise([sample("irrelevant", 0.1)])


def test_decide_keeps_the_current_threshold_when_both_sides_have_the_margin() -> None:
    assert decide(summary((0.30, 0.5, 0.4), (0.0, 0.10, 0.05))) == ("keep", 0.2)


def test_decide_keeps_when_the_relevant_minimum_sits_exactly_on_its_margin_but_not_when_the_irrelevant_maximum_does() -> None:
    assert decide(summary((0.25, 0.5, 0.4), (0.0, 0.149, 0.05))) == ("keep", 0.2)
    assert decide(summary((0.25, 0.5, 0.4), (0.0, 0.15, 0.05))) == ("change", 0.2)


def test_decide_changes_to_the_midpoint_rounded_to_five_hundredths() -> None:
    # irrelevant tops out at 0.28 (above the 0.15 ceiling), relevant starts at 0.46: midpoint 0.37 rounds to 0.35.
    assert decide(summary((0.46, 0.7, 0.6), (0.0, 0.28, 0.1))) == ("change", 0.35)


def test_decide_lowers_the_threshold_when_the_relevant_scores_are_low() -> None:
    # relevant starts at 0.18 (below 0.25), irrelevant tops out at 0.04: midpoint 0.11 rounds to 0.10.
    assert decide(summary((0.18, 0.4, 0.3), (0.0, 0.04, 0.02))) == ("change", 0.10)


def test_decide_clamps_to_the_lower_bound() -> None:
    assert decide(summary((0.04, 0.4, 0.2), (0.0, 0.01, 0.0))) == ("change", 0.05)


def test_decide_clamps_to_the_upper_bound() -> None:
    assert decide(summary((0.95, 0.99, 0.97), (0.7, 0.9, 0.8))) == ("change", 0.6)


def test_decide_is_blocked_when_the_groups_overlap() -> None:
    assert decide(summary((0.20, 0.5, 0.3), (0.0, 0.25, 0.1))) == ("blocked", None)
    assert decide(summary((0.25, 0.5, 0.3), (0.0, 0.25, 0.1))) == ("blocked", None)


def test_decide_takes_the_current_value_and_margin_as_arguments() -> None:
    assert decide(summary((0.46, 0.7, 0.6), (0.0, 0.28, 0.1)), current=0.35, margin=0.05) == ("keep", 0.35)
    assert decide(summary((0.30, 0.5, 0.4), (0.0, 0.10, 0.05)), current=0.2, margin=0.2) == ("change", 0.2)


def test_the_evidence_writer_prints_only_allow_listed_fields() -> None:
    secret = "sk-or-v1-" + "a" * 40
    samples = [sample("relevant", 0.5, "reactor"), sample("irrelevant", 0.1, "greeting")]
    text = render_evidence(samples, [], summarise(samples), ("keep", 0.2), embeddings=2, current=0.2)
    assert "reactor" in text and "greeting" in text and "keep" in text
    assert secret not in text and "sk-" not in text and "Authorization" not in text


def test_the_evidence_writer_rejects_a_label_that_looks_like_a_secret() -> None:
    bad = Sample(kind="relevant", label="sk-or-v1-" + "b" * 30, weight=0.3, term=0.0, vector=0.4, similarity=0.4)
    with pytest.raises(ValueError, match="label"):
        render_evidence([bad, sample("irrelevant", 0.1)], [], summarise([bad, sample("irrelevant", 0.1)]), ("keep", 0.2), embeddings=2, current=0.2)


def test_the_query_budget_is_checked_before_a_call_is_made() -> None:
    budget = probe.QueryBudget(limit=2)
    budget.spend()
    budget.spend()
    with pytest.raises(RuntimeError, match="budget"):
        budget.spend()
    assert budget.used == 2


def test_the_planned_run_fits_inside_the_budget() -> None:
    assert len(probe.RELEVANT) == 5 and len(probe.IRRELEVANT) == 5
    planned = len(probe.RELEVANT) + len(probe.IRRELEVANT) + 2 * len(probe.WEIGHT_PROBES) + probe.SUPPLEMENTARY_COUNT
    assert planned <= probe.QUERY_LIMIT - 4, "room is left for retries"
    assert probe.QUERY_LIMIT == 24


def test_pick_sample_takes_the_best_chunk_that_holds_the_planted_token() -> None:
    question = probe.Question("fact", "text", "Zorblax-4417")
    chunks = [
        {"content": "other paragraph", "similarity": 0.9, "term_similarity": 0.9, "vector_similarity": 0.9},
        {"content": "The Zorblax-4417 reactor", "similarity": 0.3, "term_similarity": 0.1, "vector_similarity": 0.4},
        {"content": "Zorblax-4417 again", "similarity": 0.2, "term_similarity": 0.0, "vector_similarity": 0.3},
    ]
    picked = probe.pick_sample("relevant", question, 0.3, chunks)
    assert (picked.similarity, picked.term, picked.vector, picked.holds_fact) == (0.3, 0.1, 0.4, True)


def test_pick_sample_scores_a_missing_fact_chunk_as_zero_and_an_irrelevant_question_by_its_best_chunk() -> None:
    missing = probe.pick_sample("relevant", probe.Question("fact", "t", "Zorblax-4417"), 0.3, [{"content": "x", "similarity": 0.8}])
    assert missing.similarity == 0.0 and missing.holds_fact is False
    best = probe.pick_sample("irrelevant", probe.Question("off", "t"), 0.3, [{"content": "a", "similarity": 0.1}, {"content": "b", "similarity": 0.12, "term_similarity": None}])
    assert best.similarity == 0.12 and best.term == 0.0
    nothing = probe.pick_sample("irrelevant", probe.Question("off", "t"), 0.3, [])
    assert nothing.similarity == 0.0 and nothing.holds_fact is True
