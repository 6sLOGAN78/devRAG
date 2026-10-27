#!/usr/bin/env python3
"""One-off calibration of the default similarity threshold with real ``baai/bge-m3`` vectors (plan 05-06; RETR-14, research A6, Pitfalls 3 and 12).

Run it once from the repository root against the dev stack::

    uv run python scripts/probe/calibrate_retrieval.py

It registers a throw-away account, saves the OpenRouter provider (embedding model only, so it makes no chat call), builds a dataset from the
planted TXT and PDF, then asks 5 relevant and 5 irrelevant questions through ``POST /api/v1/datasets/search`` with the threshold at 0 and rerank
off, and records term, vector and blended similarity of the decisive chunk for each. The pure ``summarise`` and ``decide`` functions turn those
scores into one of ``keep`` / ``change`` / ``blocked``; the result is written to ``05-CALIBRATION.md``.

The provider key is read from ``docker/.env``, is sent only in the provider PUT body and is never printed, logged or written: the evidence is
rendered from allow-listed fields of ``Sample`` and is checked against the key before it is written. At most ``QUERY_LIMIT`` query embeddings are
spent, counted from this process's own calls. This is a manual script, outside the gate budget of D-06.
"""

from __future__ import annotations

import math
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

EVIDENCE_PATH = REPO / ".planning" / "phases" / "05-retrieval-and-cited-chat-core-value-gate" / "05-CALIBRATION.md"
MISSING_KEY_MESSAGE = "OPENROUTER_API_KEY is missing from docker/.env; the calibration probe cannot run"
QUERY_LIMIT = 24
WEIGHT = 0.3
MARGIN = 0.05
LOWEST, HIGHEST = 0.05, 0.6
STEP = 0.05
RETRYABLE = {429, 502, 503, 504}
RETRY_DEADLINE_SECONDS = 120.0
RETRY_INTERVAL_SECONDS = 4.0
PROVIDER = "OpenRouter"

RULE = (
    "keep the current threshold T when the highest irrelevant similarity is below T - 0.05 and the lowest relevant similarity is at or above "
    "T + 0.05; otherwise move it to the midpoint of those two values, rounded to the nearest 0.05 and clamped to [0.05, 0.6]; if the lowest "
    "relevant similarity is not above the highest irrelevant similarity the threshold cannot separate them and the outcome is blocked "
    "(the weights, the tokenizer or the embedding model are the problem)"
)

_SECRET_SHAPE = re.compile(r"sk-|[A-Za-z0-9_\-]{32,}")


@dataclass(frozen=True)
class Question:
    """A short label (the only text that reaches the evidence file), the wording sent, and the planted token the answer chunk holds."""

    label: str
    text: str
    token: str | None = None


# Five relevant questions, worded without the rare token so that meaning, not the token, has to carry the match.
RELEVANT: tuple[Question, ...] = (
    Question("coolant temperature of the reactor (TXT)", "What temperature does the cooling fluid of the nuclear plant reach?", "Zorblax-4417"),
    Question("depth of the glacier ice (TXT)", "How thick is the layer of frozen water measured by the glacier expedition?", "Quenthar-9082"),
    Question("weekend bakery sales (TXT)", "How much bread does the neighbourhood bakery sell during a weekend?", "Plimsby-3356"),
    Question("height of the lighthouse (PDF)", "How high is the lighthouse above the bay?", "Brantwell-6130"),
    Question("quince harvest of the orchard (PDF)", "How much fruit was harvested by the orchard?", "Oskarine-8847"),
)

# Five irrelevant questions: off-topic, a nonsense string, another domain, only stopwords, a greeting.
IRRELEVANT: tuple[Question, ...] = (
    Question("off-topic news question", "Which volcano erupted beneath Iceland yesterday?"),
    Question("nonsense token string", "qzxv blorp wuggle snarf 90817 mnbvq"),
    Question("another domain (databases)", "How do I configure a PostgreSQL replication slot for logical decoding?"),
    Question("stopwords only", "is it the one that was in the of a for"),
    Question("short generic greeting", "Hello there, how are you?"),
)

SUPPLEMENTARY_COUNT = 5  # the wording of the planted-fact tests (D-07, rare token included), recorded as supplementary information

WEIGHT_PROBES: tuple[str, ...] = (RELEVANT[0].label, RELEVANT[3].label)  # also asked at weights 0 and 1


@dataclass(frozen=True)
class Sample:
    """One measured question. These fields, and only these, are written to the evidence file."""

    kind: str  # relevant | irrelevant | weight | supplementary
    label: str
    weight: float
    term: float
    vector: float
    similarity: float
    holds_fact: bool = True


class QueryBudget:
    """Counts query embeddings where they are spent and refuses the call that would exceed the limit."""

    def __init__(self, limit: int = QUERY_LIMIT) -> None:
        self.limit = limit
        self.used = 0

    def spend(self) -> None:
        if self.used >= self.limit:
            raise RuntimeError(f"query embedding budget of {self.limit} is spent")
        self.used += 1


# ----------------------------------------------------------------------------- pure decision logic


def _group(samples: Sequence[Sample], kind: str) -> dict[str, float]:
    values = [s.similarity for s in samples if s.kind == kind]
    if not values:
        raise ValueError(f"no {kind} samples to summarise")
    return {"min": min(values), "max": max(values), "mean": sum(values) / len(values)}


def summarise(samples: Sequence[Sample]) -> dict[str, dict[str, float]]:
    """Minimum, maximum and mean of the blended similarity of the relevant and of the irrelevant samples."""
    return {"relevant": _group(samples, "relevant"), "irrelevant": _group(samples, "irrelevant")}


def decide(summary: Mapping[str, Mapping[str, float]], current: float = 0.2, margin: float = MARGIN) -> tuple[str, float | None]:
    """``("keep", current)``, ``("change", t)`` or ``("blocked", None)``.

    ``blocked`` means the two groups overlap, so no threshold separates them. ``change`` carries the midpoint of the two ranges rounded to the
    nearest 0.05 and clamped to [0.05, 0.6]; the rounded value can equal ``current`` when the ranges are close to it but short of the margin,
    in which case no code changes.
    """
    relevant_low = summary["relevant"]["min"]
    irrelevant_high = summary["irrelevant"]["max"]
    if relevant_low <= irrelevant_high:
        return ("blocked", None)
    eps = 1e-9
    if irrelevant_high < current - margin - eps and relevant_low >= current + margin - eps:
        return ("keep", current)
    midpoint = (relevant_low + irrelevant_high) / 2.0
    rounded = round(round(midpoint / STEP) * STEP, 2)
    return ("change", min(HIGHEST, max(LOWEST, rounded)))


def pick_sample(kind: str, question: Question, weight: float, chunks: Sequence[Mapping[str, Any]]) -> Sample:
    """The decisive chunk of one answer: the best chunk holding the planted token (relevant), or the best chunk of all (irrelevant).

    A relevant question whose fact chunk was not returned scores zero with ``holds_fact`` false, so a retrieval miss counts against the threshold.
    """

    def number(chunk: Mapping[str, Any], key: str) -> float:
        value = chunk.get(key)
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else 0.0

    pool = [c for c in chunks if question.token in str(c.get("content", ""))] if question.token else list(chunks)
    if not pool:
        return Sample(kind, question.label, weight, 0.0, 0.0, 0.0, holds_fact=question.token is None)
    best = max(pool, key=lambda c: number(c, "similarity"))
    return Sample(kind, question.label, weight, number(best, "term_similarity"), number(best, "vector_similarity"), number(best, "similarity"))


# ----------------------------------------------------------------------------- evidence


def _check_label(label: str) -> str:
    if _SECRET_SHAPE.search(label):
        raise ValueError("a sample label looks like a credential and is not written")
    return label.replace("|", "/")


def _rows(samples: Sequence[Sample]) -> list[str]:
    lines = ["| Label | Weight | Term | Vector | Blended | Fact chunk returned |", "|---|---|---|---|---|---|"]
    for s in samples:
        lines.append(f"| {_check_label(s.label)} | {s.weight:.1f} | {s.term:.4f} | {s.vector:.4f} | {s.similarity:.4f} | {'yes' if s.holds_fact else 'no'} |")
    return lines


def render_evidence(
    samples: Sequence[Sample],
    extras: Sequence[Sample],
    summary: Mapping[str, Mapping[str, float]],
    decision: tuple[str, float | None],
    *,
    embeddings: int,
    current: float,
    notes: Sequence[str] = (),
) -> str:
    """The markdown evidence file. Built only from allow-listed fields: labels, weights and scores, counts and the outcome."""
    outcome, value = decision
    relevant = [s for s in samples if s.kind == "relevant"]
    irrelevant = [s for s in samples if s.kind == "irrelevant"]
    lines = [
        "# Phase 5 retrieval calibration (plan 05-06)",
        "",
        "Measured once with the real `baai/bge-m3` embedding model (1024 dimensions) on the planted corpus: one TXT of six paragraphs and one",
        "three-page PDF (`test/helpers/planted.py`), threshold 0 and rerank off, so every returned chunk is scored. Blended similarity is",
        "`(1 - w) * term + w * vector` with w = 0.3. Question wording is not recorded, only a short label.",
        "",
        "## Relevant questions (worded without the planted token)",
        "",
        *_rows(relevant),
        "",
        "## Irrelevant questions",
        "",
        *_rows(irrelevant),
    ]
    weights = [s for s in extras if s.kind == "weight"]
    if weights:
        lines += ["", "## Weight probes (two relevant questions at weight 0 = term only and 1 = vector only)", "", *_rows(weights)]
    supplementary = [s for s in extras if s.kind == "supplementary"]
    if supplementary:
        lines += ["", "## Supplementary: the wording of the planted-fact tests (rare token included)", "", *_rows(supplementary)]
    lines += [
        "",
        "## Summary of the blended similarity",
        "",
        "| Group | Min | Max | Mean |",
        "|---|---|---|---|",
        f"| relevant | {summary['relevant']['min']:.4f} | {summary['relevant']['max']:.4f} | {summary['relevant']['mean']:.4f} |",
        f"| irrelevant | {summary['irrelevant']['min']:.4f} | {summary['irrelevant']['max']:.4f} | {summary['irrelevant']['mean']:.4f} |",
        "",
        "## Rule",
        "",
        f"Current default T = {current:.2f}, margin 0.05: {RULE}.",
        "",
        "## Outcome",
        "",
        f"**{outcome}**" + (f", threshold {value:.2f}" if value is not None else ""),
        "",
        f"Query embeddings spent: {embeddings} of {QUERY_LIMIT} allowed (outside the live budget of D-06).",
    ]
    if notes:
        lines += ["", "## Notes", "", *[f"- {n}" for n in notes]]
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------- the live run (manual; needs the dev stack)


def _api_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _retrying(attempt: Any, describe: str) -> Any:
    """Poll ``attempt`` until it returns a truthy result; it returns ``None`` for a retryable provider failure."""
    from test.helpers.wait import wait_until

    return wait_until(attempt, timeout=RETRY_DEADLINE_SECONDS, interval=RETRY_INTERVAL_SECONDS, describe=lambda: describe)


def _save_provider(http: Any, token: str, key: str, embed_model: str, chat_model: str | None = None) -> None:
    """Save embedding and, for the adherence probe, an optional chat model."""
    models = [{"name": embed_model, "type": "embedding"}]
    if chat_model is not None:
        models.append({"name": chat_model, "type": "chat"})
    body = {"provider": PROVIDER, "api_key": key, "models": models}

    def attempt() -> dict[str, bool] | None:
        http.cookies.clear()
        response = http.put("/api/v1/providers", headers=_api_headers(token), json=body, timeout=90.0)
        if response.status_code in RETRYABLE:
            return None
        if response.status_code != 200 or response.json().get("code") != 0:
            reason = (response.json().get("data") or {}).get("reason") if response.headers.get("content-type", "").startswith("application/json") else None
            raise RuntimeError(f"the provider could not be saved (HTTP {response.status_code}, reason {reason})")
        return {"saved": True}

    _retrying(attempt, "OpenRouter did not accept the provider save in time")


def _ask(http: Any, token: str, dataset_id: str, question: Question, weight: float, budget: QueryBudget) -> list[dict[str, Any]]:
    body = {"dataset_ids": [dataset_id], "question": question.text, "similarity_threshold": 0.0, "vector_similarity_weight": weight, "size": 100}

    def attempt() -> dict[str, list[dict[str, Any]]] | None:
        budget.spend()
        http.cookies.clear()
        response = http.post("/api/v1/datasets/search", headers=_api_headers(token), json=body, timeout=90.0)
        if response.status_code in RETRYABLE:
            return None
        if response.status_code != 200 or response.json().get("code") != 0:
            raise RuntimeError(f"the search failed (HTTP {response.status_code})")
        return {"chunks": list(response.json()["data"]["chunks"])}

    return _retrying(attempt, "the search did not succeed in time")["chunks"]


def supplementary_questions() -> tuple[Question, ...]:
    from test.helpers.planted import FACTS, PDF_FACTS

    facts = [*FACTS[:3], PDF_FACTS[1], PDF_FACTS[2]]
    questions = tuple(Question(f"planted-fact wording: {f.token}", f.question, f.token) for f in facts)
    if len(questions) != SUPPLEMENTARY_COUNT:
        raise ValueError("supplementary question count differs from the probe budget")
    return questions


def run() -> int:
    import httpx

    from test.conftest import stack_env
    from test.helpers.accounts import AccountRegistry
    from test.helpers.ingest import dataset_row, start_parse, upload_text, wait_run
    from test.helpers.planted import planted_pdf, planted_txt

    env = stack_env()
    key = env.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        print(MISSING_KEY_MESSAGE, file=sys.stderr)
        return 2
    embed_model = env.get("LIVE_EMBED_MODEL") or "baai/bge-m3"
    dimension = int(env.get("LIVE_EXPECTED_DIM") or 1024)
    base_url = f"http://127.0.0.1:{env.get('SVR_WEB_HTTP_PORT', '8080')}"

    from api.apps.restful_apis.retrieval_api import SearchBody

    current = float(SearchBody.model_fields["similarity_threshold"].default)
    budget = QueryBudget()
    supplementary = supplementary_questions()
    registry = AccountRegistry(base_url)
    samples: list[Sample] = []
    extras: list[Sample] = []
    notes: list[str] = []
    try:
        with httpx.Client(base_url=base_url, timeout=90.0, follow_redirects=False) as http:
            owner = registry.register(prefix="calibrate")
            token = owner.token
            _save_provider(http, token, key, embed_model)
            embed_id = f"{embed_model}@{PROVIDER}"
            http.cookies.clear()
            defaults = http.patch("/api/v1/models/default", headers=_api_headers(token), json={"embedding": embed_id})
            if defaults.status_code != 200:
                raise RuntimeError(f"the default embedding model was refused (HTTP {defaults.status_code})")
            http.cookies.clear()
            created = http.post("/api/v1/datasets", headers=_api_headers(token), json={"name": "Calibration knowledge base"})
            if created.status_code != 200 or created.json().get("code") != 0:
                raise RuntimeError(f"the dataset could not be created (HTTP {created.status_code})")
            dataset = created.json()["data"]
            if dataset["embedding_dimension"] != dimension:
                raise RuntimeError("the dataset's embedding dimension is not the expected one")
            dataset_id = dataset["id"]
            txt = upload_text(http, owner, dataset_id, planted_txt(), "calibration-planted.txt", mime="text/plain")
            pdf = upload_text(http, owner, dataset_id, planted_pdf(), "calibration-planted.pdf", mime="application/pdf")
            started = start_parse(http, owner, dataset_id, [txt["id"], pdf["id"]])
            if started.status_code != 200:
                raise RuntimeError(f"parsing could not be started (HTTP {started.status_code})")
            wait_run(http, owner, dataset_id, txt["id"], "3", timeout=300)
            wait_run(http, owner, dataset_id, pdf["id"], "3", timeout=300)
            notes.append(f"corpus: {dataset_row(http, owner, dataset_id)['chunk_num']} chunks in 2 documents")

            for question in RELEVANT:
                samples.append(pick_sample("relevant", question, WEIGHT, _ask(http, token, dataset_id, question, WEIGHT, budget)))
            for question in IRRELEVANT:
                samples.append(pick_sample("irrelevant", question, WEIGHT, _ask(http, token, dataset_id, question, WEIGHT, budget)))
            for question in RELEVANT:
                if question.label in WEIGHT_PROBES:
                    for weight in (0.0, 1.0):
                        extras.append(pick_sample("weight", question, weight, _ask(http, token, dataset_id, question, weight, budget)))
            for question in supplementary:
                extras.append(pick_sample("supplementary", question, WEIGHT, _ask(http, token, dataset_id, question, WEIGHT, budget)))
    finally:
        registry.cleanup()

    summary = summarise(samples)
    decision = decide(summary, current=current)
    text = render_evidence(samples, extras, summary, decision, embeddings=budget.used, current=current, notes=notes)
    if key in text:
        raise RuntimeError("the evidence text contains the provider key and was not written")
    EVIDENCE_PATH.write_text(text, encoding="utf-8")
    outcome, value = decision
    print(f"calibration outcome={outcome} threshold={value} embeddings={budget.used}/{QUERY_LIMIT} evidence={EVIDENCE_PATH.relative_to(REPO)}")
    return 0 if outcome != "blocked" else 3


if __name__ == "__main__":
    sys.exit(run())
