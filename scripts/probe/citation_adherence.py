#!/usr/bin/env python3
"""One-off live citation adherence measurement through the real completion route.

Only labels, marker indices and counts enter the evidence file. The provider key is
read from docker/.env, sent in the provider PUT body, and never rendered or logged.
"""
from __future__ import annotations

import hashlib
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from rag.prompts.citations import valid_indices  # noqa: E402
from rag.prompts.generator import CITATION_RULES  # noqa: E402
from scripts.probe.calibrate_retrieval import PROVIDER, RETRYABLE, _api_headers, _retrying, _save_provider  # noqa: E402

EVIDENCE_PATH = REPO / ".planning/phases/05-retrieval-and-cited-chat-core-value-gate/05-ADHERENCE.md"
INITIAL_MODEL = "meta-llama/llama-3.1-8b-instruct"
SWITCH_MODEL = "openai/gpt-4o-mini"
CALL_LIMIT = 20
REPETITIONS = 3


@dataclass(frozen=True)
class Result:
    valid_markers: tuple[int, ...]
    cites_planted: bool
    no_marker: bool
    fallback_inserted: bool


@dataclass(frozen=True)
class Sample:
    label: str
    repetition: int
    result: Result


def classify(
    answer_text: str,
    reference_chunks: Sequence[Mapping[str, Any]],
    planted_token: str,
    *,
    keywords: Sequence[str] = (),
    usage: Mapping[str, Any] | None = None,
) -> Result:
    """Judge a final answer against the chunk indices the model could cite."""
    indexed = {chunk["index"]: chunk for chunk in reference_chunks if isinstance(chunk.get("index"), int)}
    markers = tuple(index for index in valid_indices(answer_text, max(indexed, default=-1) + 1) if index in indexed)
    fallback = (usage or {}).get("citations") == "inserted"
    cites = bool(markers) and all(word.lower() in answer_text.lower() for word in keywords) and any(
        planted_token in str(indexed[index].get("content", "")) for index in markers
    )
    return Result(markers, cites, not markers or fallback, fallback and bool(markers))


def summarise(results: Sequence[Result]) -> dict[str, int]:
    return {
        "total": len(results),
        "cites_planted_count": sum(result.cites_planted for result in results),
        "no_marker_count": sum(result.no_marker for result in results),
        "fallback_repaired_count": sum(result.fallback_inserted for result in results),
    }


def decide(summary: Mapping[str, int], threshold: int = 14, max_no_marker: int = 2, model: str = INITIAL_MODEL) -> tuple[str, str]:
    """Use the fixed 14/15 and 2/15 boundary, including fallback signals."""
    if summary["total"] != 15:
        raise ValueError("citation adherence needs exactly 15 completed turns")
    if summary["cites_planted_count"] < threshold or summary["no_marker_count"] > max_no_marker:
        return "switch", SWITCH_MODEL
    return "keep", model


class ChatBudget:
    def __init__(self) -> None:
        self.used = 0

    def spend(self) -> None:
        if self.used >= CALL_LIMIT:
            raise RuntimeError("citation probe chat-call limit reached")
        self.used += 1


def _post(http: Any, token: str, path: str, body: Mapping[str, Any], *, timeout: float = 90.0) -> dict[str, Any]:
    http.cookies.clear()
    response = http.post(path, headers=_api_headers(token), json=body, timeout=timeout)
    if response.status_code != 200 or response.json().get("code") != 0:
        data = response.json().get("data") or {}
        reason = data.get("reason") if isinstance(data, dict) else None
        raise RuntimeError(f"probe request failed (HTTP {response.status_code}, reason {reason})")
    return response.json()["data"]


def _assistant(http: Any, token: str, dataset_id: str, model: str) -> str:
    body = {
        "name": f"Adherence {model.rsplit('/', 1)[-1]}", "llm_id": f"{model}@{PROVIDER}", "kb_ids": [dataset_id],
        "similarity_threshold": 0.2, "vector_similarity_weight": 0.3, "top_n": 12,
        "llm_setting": {"temperature": 0, "max_tokens": 512},
    }
    return str(_post(http, token, "/api/v1/chats", body)["id"])


def _turn(http: Any, token: str, chat_id: str, question: str, budget: ChatBudget) -> dict[str, Any]:
    body = {"chat_id": chat_id, "message": question, "stream": False}

    def attempt() -> dict[str, Any] | None:
        budget.spend()
        http.cookies.clear()
        response = http.post("/api/v1/chat/completions", headers=_api_headers(token), json=body, timeout=90.0)
        if response.status_code in RETRYABLE:
            return None
        if response.status_code != 200 or response.json().get("code") != 0:
            data = response.json().get("data") or {}
            reason = data.get("reason") if isinstance(data, dict) else None
            raise RuntimeError(f"live completion failed (HTTP {response.status_code}, reason {reason})")
        return dict(response.json()["data"])

    return _retrying(attempt, "live chat did not answer within the retry deadline")


def _measure(http: Any, token: str, chat_id: str, budget: ChatBudget) -> tuple[list[Sample], dict[str, int]]:
    from test.helpers.planted import FACTS, PDF_FACTS

    facts = [*FACTS[:3], PDF_FACTS[1], PDF_FACTS[2]]
    samples: list[Sample] = []
    for fact in facts:
        for repetition in range(1, REPETITIONS + 1):
            final = _turn(http, token, chat_id, fact.question, budget)
            if final.get("empty") or final.get("finish") != "complete":
                raise RuntimeError("a planted-fact turn did not complete with retrieved context")
            reference = final.get("reference") or {}
            result = classify(str(final["answer"]), reference.get("chunks") or [], fact.token,
                              keywords=fact.keywords[1:], usage=final.get("usage") or {})
            samples.append(Sample(fact.token, repetition, result))
            session = _post_read(http, token, chat_id, str(final["session_id"]))
            saved = session["messages"][-1]
            if saved.get("id") != final.get("message_id") or saved.get("empty") or not saved.get("usage"):
                raise RuntimeError("a probe answer was not persisted with usage")
    if len(samples) != 15 or budget.used > CALL_LIMIT:
        raise RuntimeError("probe did not meet its 15-result and 20-call bounds")
    return samples, summarise([sample.result for sample in samples])


def _post_read(http: Any, token: str, chat_id: str, session_id: str) -> dict[str, Any]:
    http.cookies.clear()
    response = http.get(f"/api/v1/chats/{chat_id}/sessions/{session_id}", headers=_api_headers(token), timeout=30.0)
    if response.status_code != 200 or response.json().get("code") != 0:
        raise RuntimeError(f"probe session read failed (HTTP {response.status_code})")
    return response.json()["data"]


def render_evidence(runs: Sequence[tuple[str, Sequence[Sample], Mapping[str, int], int]], outcome: tuple[str, str]) -> str:
    """Render only controlled model labels, planted labels, booleans, indices and counts."""
    allowed_models = {INITIAL_MODEL, SWITCH_MODEL}
    allowed_labels = {"Zorblax-4417", "Quenthar-9082", "Plimsby-3356", "Brantwell-6130", "Oskarine-8847"}
    lines = [
        "# Phase 5 live citation adherence (plan 05-13)", "",
        "Five planted-fact questions were asked three times per model through the real completion route with temperature 0.",
        "A result cites the planted chunk when a valid final marker points to its reference chunk and the answer contains the numeric fact.",
        "A fallback-inserted marker counts as a raw no-marker answer for the switch rule.", "",
        "Rule: keep the 8B model only with at least 14 of 15 planted citations and at most 2 raw no-marker answers; otherwise test `openai/gpt-4o-mini` once.", "",
    ]
    for model, samples, summary, calls in runs:
        if model not in allowed_models or len(samples) != 15 or calls > CALL_LIMIT:
            raise ValueError("invalid adherence run metadata")
        lines += [f"## {model}", "", "| Fact label | Run | Valid indices | Cites planted | Raw no marker | Fallback repaired |",
                  "|---|---:|---|---|---|---|"]
        for sample in samples:
            if sample.label not in allowed_labels or sample.repetition not in (1, 2, 3):
                raise ValueError("invalid adherence sample metadata")
            result = sample.result
            indices = ",".join(str(index) for index in result.valid_markers) or "none"
            lines.append(f"| {sample.label} | {sample.repetition} | {indices} | {'yes' if result.cites_planted else 'no'} | "
                         f"{'yes' if result.no_marker else 'no'} | {'yes' if result.fallback_inserted else 'no'} |")
        lines += ["", f"Planted citations: {summary['cites_planted_count']}/15; raw no-marker: {summary['no_marker_count']}/15; "
                  f"fallback repaired: {summary['fallback_repaired_count']}/15; chat requests: {calls}/{CALL_LIMIT} maximum.", ""]
    if outcome[1] not in allowed_models or outcome[0] not in {"keep", "switch"}:
        raise ValueError("invalid adherence outcome")
    digest = hashlib.sha256(CITATION_RULES.encode()).hexdigest()
    lines += ["## Outcome", "", f"**{outcome[0]}**: {outcome[1]}", "", f"Pinned `CITATION_RULES` SHA-256: `{digest}`.", "",
              "Standing gate signal for plan 05-25: at least 6 of 7 planted-fact turns cite the planted chunk."]
    return "\n".join(lines) + "\n"


def run() -> int:
    import httpx

    from test.conftest import stack_env
    from test.helpers.accounts import AccountRegistry
    from test.helpers.ingest import start_parse, upload_text, wait_run
    from test.helpers.planted import planted_pdf, planted_txt

    env = stack_env()
    key = env.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is missing from docker/.env; the live adherence probe cannot run")
    initial = env.get("LIVE_CHAT_MODEL") or INITIAL_MODEL
    if initial not in {INITIAL_MODEL, SWITCH_MODEL}:
        raise RuntimeError("LIVE_CHAT_MODEL is outside the two-model adherence decision")
    embed_model = env.get("LIVE_EMBED_MODEL") or "baai/bge-m3"
    dimension = int(env.get("LIVE_EXPECTED_DIM") or 1024)
    base_url = f"http://127.0.0.1:{env.get('SVR_WEB_HTTP_PORT', '8080')}"
    registry = AccountRegistry(base_url)
    runs: list[tuple[str, Sequence[Sample], Mapping[str, int], int]] = []
    try:
        with httpx.Client(base_url=base_url, timeout=90.0, follow_redirects=False) as http:
            owner = registry.register(prefix="adherence")
            token = owner.token
            _save_provider(http, token, key, embed_model, chat_model=initial)
            http.cookies.clear()
            defaults = http.patch("/api/v1/models/default", headers=_api_headers(token), json={"embedding": f"{embed_model}@{PROVIDER}"})
            if defaults.status_code != 200:
                raise RuntimeError(f"probe embedding default was refused (HTTP {defaults.status_code})")
            dataset = _post(http, token, "/api/v1/datasets", {"name": "Citation adherence knowledge base"})
            if dataset["embedding_dimension"] != dimension:
                raise RuntimeError("probe dataset embedding dimension differs from the configured live dimension")
            dataset_id = str(dataset["id"])
            txt = upload_text(http, owner, dataset_id, planted_txt(), "adherence-planted.txt", mime="text/plain")
            pdf = upload_text(http, owner, dataset_id, planted_pdf(), "adherence-planted.pdf", mime="application/pdf")
            started = start_parse(http, owner, dataset_id, [txt["id"], pdf["id"]])
            if started.status_code != 200:
                raise RuntimeError(f"probe parsing could not start (HTTP {started.status_code})")
            wait_run(http, owner, dataset_id, txt["id"], "3", timeout=300)
            wait_run(http, owner, dataset_id, pdf["id"], "3", timeout=300)

            chat_id = _assistant(http, token, dataset_id, initial)
            budget = ChatBudget()
            samples, summary = _measure(http, token, chat_id, budget)
            runs.append((initial, samples, summary, budget.used))
            outcome = decide(summary, model=initial)
            if outcome[0] == "switch" and initial != SWITCH_MODEL:
                _save_provider(http, token, key, embed_model, chat_model=SWITCH_MODEL)
                chat_id = _assistant(http, token, dataset_id, SWITCH_MODEL)
                second_budget = ChatBudget()
                second_samples, second_summary = _measure(http, token, chat_id, second_budget)
                runs.append((SWITCH_MODEL, second_samples, second_summary, second_budget.used))
                outcome = ("switch", SWITCH_MODEL)
    finally:
        registry.cleanup()

    evidence = render_evidence(runs, outcome)
    if key in evidence:
        raise RuntimeError("provider key appeared in evidence; refusing to write")
    EVIDENCE_PATH.write_text(evidence, encoding="utf-8")
    print(f"adherence outcome={outcome[0]} model={outcome[1]} results={sum(len(run[1]) for run in runs)} evidence={EVIDENCE_PATH.relative_to(REPO)}")
    final_summary = runs[-1][2]
    return 0 if decide(final_summary, model=outcome[1])[0] == "keep" else 3


if __name__ == "__main__":
    sys.exit(run())
