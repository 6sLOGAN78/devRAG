"""Phase 5 bounded real-provider proof: documents, retrieval, rerank and cited chat through ingress.

The credential is read by live_env and only sent in the provider PUT body. Assertions and evidence
contain counts and booleans. This tier fails without a key; no inference is mocked. Run once with -x.
"""
# ruff: noqa: F811
from __future__ import annotations

import json
import re
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from test.helpers.accounts import Account
from test.helpers.chat_stream import read_stream
from test.helpers.ingest import start_parse, upload_text, wait_run
from test.helpers.planted import FACTS, PDF_FACTS, Fact, off_topic_question, planted_pdf, planted_txt
from test.helpers.wait import wait_until
from test.testcases.conftest import BASE_URL, compose
from test.testcases.test_live_models import (  # noqa: F401
    LiveEnv,
    Recorder,
    bound_database,
    call,
    client,
    data_of,
    ingress,
    leaks,
    live_env,
    owner,
    recorder,
    sql,
    started_at,
)

pytestmark = pytest.mark.live_model
CHAT_TURN_CAP = 15
QUERY_EMBED_CAP = 17  # The repeated 14 in one acceptance bullet is superseded by the plan's explicit D-06 refinement.
INGEST_CHUNK_CAP = 72
TEI_MODEL = "BAAI/bge-reranker-base"
COMPLETIONS = "/api/v1/chat/completions"
STATE: dict[str, Any] = {"turns": 0, "citations": [], "sessions": set(), "rerank_requests": 0}


def logs(service: str, since: str) -> str:
    result = compose("logs", "--no-color", "--since", since, service)
    assert result.returncode == 0
    return result.stdout + result.stderr


def usage_count(service: str, since: str, tenant: str, model: str) -> int:
    count = 0
    for line in logs(service, since).splitlines():
        start = line.find('{')
        if start < 0:
            continue
        try:
            row = json.loads(line[start:])
        except (ValueError, TypeError):
            continue
        count += int(row.get("msg") == "llm usage" and row.get("tenant") == tenant and row.get("model") == model)
    return count


def request(client: httpx.Client, who: Account, method: str, path: str, body: Any = None) -> Any:
    response = call(client, method, path, who.token, body)
    # Do not put provider payloads in assertion diagnostics.
    assert response.status_code == 200, response.status_code
    envelope = response.json()
    assert envelope["code"] == 0
    return envelope["data"]


@pytest.fixture(scope="module")
def world(client: httpx.Client, owner: Account, live_env: LiveEnv, started_at: str) -> SimpleNamespace:
    request(client, owner, "PUT", "/api/v1/providers", {"provider": "OpenRouter", "api_key": live_env.key,
        "models": [{"name": live_env.chat_model, "type": "chat"}, {"name": live_env.embed_model, "type": "embedding"}]})
    request(client, owner, "PUT", "/api/v1/providers", {"provider": "TEI", "models": [{"name": TEI_MODEL, "type": "rerank"}]})
    request(client, owner, "PATCH", "/api/v1/models/default", {"chat": live_env.chat_id, "embedding": live_env.embed_id})
    dataset = request(client, owner, "POST", "/api/v1/datasets", {"name": "Phase 5 live planted facts"})
    docs = [upload_text(client, owner, dataset["id"], planted_txt(), "facts.txt"),
        upload_text(client, owner, dataset["id"], planted_pdf(), "facts.pdf", mime="application/pdf")]
    assert start_parse(client, owner, dataset["id"], [doc["id"] for doc in docs]).status_code == 200
    rows = [wait_run(client, owner, dataset["id"], doc["id"], "3", timeout=300) for doc in docs]
    chunks = sum(row["chunk_count"] for row in rows)
    assert 7 <= chunks <= INGEST_CHUNK_CAP  # Six TXT paragraphs and at least one PDF chunk (R-208).
    common = {"llm_id": live_env.chat_id, "kb_ids": [dataset["id"]], "top_n": 6, "similarity_threshold": 0.2,
        "llm_setting": {"temperature": 0}, "vector_similarity_weight": 0.3}
    on = request(client, owner, "POST", "/api/v1/chats", {"name": "Live TEI", **common, "rerank_id": f"{TEI_MODEL}@TEI"})
    off = request(client, owner, "POST", "/api/v1/chats", {"name": "Live fusion", **common})
    empty = request(client, owner, "POST", "/api/v1/chats", {"name": "Live empty", **common, "vector_similarity_weight": 0})
    STATE["app_before"] = usage_count("app", started_at, owner.tenant_id, live_env.embed_model)
    STATE["worker_before"] = usage_count("task-executor", started_at, owner.tenant_id, live_env.embed_model)
    assert STATE["worker_before"] > 0
    expected = {}
    for fact in (FACTS[0], PDF_FACTS[1]):
        result = request(client, owner, "POST", "/api/v1/datasets/search", {"dataset_ids": [dataset["id"]], "question": fact.question,
            "rerank_id": f"{TEI_MODEL}@TEI", "similarity_threshold": 0.2, "vector_similarity_weight": 0.3, "size": 6})
        assert result["rerank_applied"] is True
        matching = [hit for hit in result["chunks"] if fact.token in hit["content"]]
        assert len(matching) == 1
        expected[fact.token] = matching[0]["chunk_id"]
    try:
        yield SimpleNamespace(dataset_id=dataset["id"], on=on, off=off, empty=empty, expected=expected, chunks=chunks)
    finally:
        print("LIVE-ATTEMPT-COUNTS", json.dumps({"chat_turns": STATE["turns"], "provider_save_chat": 1,
            "query_embeddings": usage_count("app", started_at, owner.tenant_id, live_env.embed_model) - STATE["app_before"],
            "ingestion_calls": STATE["worker_before"], "rerank_requests": STATE["rerank_requests"],
            "correct_citations": sum(STATE["citations"]), "citation_samples": len(STATE["citations"])}))


def ask(client: httpx.Client, owner: Account, chat_id: str, question: str, recorder: Recorder, *, stream: bool = False, **extra: Any) -> dict:
    body = {"chat_id": chat_id, "message": question, "stream": stream, **extra}
    if not stream:
        final = request(client, owner, "POST", COMPLETIONS, body)
    else:
        # Recorder.hook buffers responses; a separate client is required for true streaming and disconnects.
        with httpx.Client(base_url=BASE_URL, timeout=90) as http:
            with http.stream("POST", COMPLETIONS, headers={"Authorization": f"Bearer {owner.token}"}, json=body) as response:
                assert response.status_code == 200
                result = read_stream(response.iter_lines())
        recorder.captured.extend(json.dumps(frame) for frame in result.frames)
        assert result.done and result.deltas_text and result.final is not None
        assert result.final["code"] == 0
        final = result.final["data"]
    STATE["sessions"].add((chat_id, final["session_id"]))
    if not final["empty"]:
        STATE["turns"] += 1
    return final


def citation_matches(final: dict, fact: Fact, expected: str | None = None) -> bool:
    chunks = final["reference"]["chunks"]
    numbers = [int(value) for value in re.findall(r"##(\d+)\$\$", final["answer"])]
    return any(0 <= number < len(chunks) and fact.token in chunks[number]["content"]
        and (expected is None or chunks[number]["chunk_id"] == expected) for number in numbers)


def assert_fact(final: dict, fact: Fact, *, expected: str | None = None, hard: bool = True) -> None:
    assert any(fact.token in chunk.get("content", "") for chunk in final["reference"]["chunks"]), "the planted source must reach generation"
    correct = citation_matches(final, fact, expected)
    STATE["citations"].append(correct)
    normalized = final["answer"].replace(",", "").casefold()
    assert all(keyword.casefold() in normalized for keyword in fact.keywords)
    if hard:
        assert correct, "the planted fact must cite its exact source chunk (D-05/D-07)"


def test_planted_txt_stream_with_real_tei(client, owner, world, recorder):
    final = ask(client, owner, world.on["id"], FACTS[0].question, recorder, stream=True)
    assert_fact(final, FACTS[0], expected=world.expected[FACTS[0].token])


def test_planted_pdf_stream_with_real_tei(client, owner, world, recorder):
    fact = PDF_FACTS[1]
    final = ask(client, owner, world.on["id"], fact.question, recorder, stream=True)
    assert_fact(final, fact, expected=world.expected[fact.token])
    cited = next(hit for hit in final["reference"]["chunks"] if hit["chunk_id"] == world.expected[fact.token])
    assert cited["positions"] and cited["page_sizes"]


@pytest.mark.parametrize("fact", [FACTS[1], PDF_FACTS[2]], ids=["txt", "pdf"])
def test_nonstream_planted_fact_without_rerank(client, owner, world, recorder, fact):
    assert_fact(ask(client, owner, world.off["id"], fact.question, recorder), fact)


def test_stop_keeps_partial_and_releases_turn(client, owner, world, recorder):
    chat_id = world.empty["id"]
    partial = None
    with httpx.Client(base_url=BASE_URL, timeout=90) as http:
        with http.stream("POST", COMPLETIONS, headers={"Authorization": f"Bearer {owner.token}"},
            json={"chat_id": chat_id, "message": FACTS[2].question, "stream": True}) as response:
            assert response.status_code == 200
            for line in response.iter_lines():
                if line.startswith("data: {"):
                    frame = json.loads(line[6:])
                    recorder.captured.append(json.dumps(frame))
                    if frame.get("code") == 0 and frame["data"].get("answer") and not frame["data"].get("final"):
                        partial = frame["data"]
                        break
    assert partial is not None
    STATE["turns"] += 1
    STATE["sessions"].add((chat_id, partial["session_id"]))
    def stopped():
        session = request(client, owner, "GET", f"/api/v1/chats/{chat_id}/sessions/{partial['session_id']}")
        message = session["messages"][-1]
        return message if message.get("finish") == "stopped" else None
    message = wait_until(stopped, timeout=30, describe=lambda: "stopped assistant partial persisted")
    assert message["content"].startswith(partial["answer"])
    STATE["stopped_session"] = partial["session_id"]


def test_off_topic_spends_no_chat_and_following_turn_is_accepted(client, owner, world, recorder, live_env, started_at):
    before = usage_count("app", started_at, owner.tenant_id, live_env.chat_model)
    final = ask(client, owner, world.empty["id"], off_topic_question(), recorder, session_id=STATE["stopped_session"])
    assert final["empty"] is True and final["reference"]["chunks"] == []
    assert final["answer"] == world.empty["prompt_config"]["empty_response"]
    assert usage_count("app", started_at, owner.tenant_id, live_env.chat_model) == before


@pytest.mark.parametrize("fact", [FACTS[3], FACTS[4], PDF_FACTS[3]], ids=["orchestra", "comet", "archive"])
def test_fresh_session_citation_sample(client, owner, world, recorder, fact):
    assert_fact(ask(client, owner, world.on["id"], fact.question, recorder), fact, hard=False)


def test_citation_standing_signal():
    assert len(STATE["citations"]) == 7 and sum(STATE["citations"]) >= 6


def test_openrouter_rerank(client, owner, world, live_env):
    # Saving a rerank model itself makes a real inference request. Count that request too.
    model = "nvidia/llama-nemotron-rerank-vl-1b-v2:free"
    STATE["rerank_requests"] += 1
    saved = call(client, "PUT", "/api/v1/providers", owner.token,
        {"provider": "OpenRouter", "models": [{"name": model, "type": "rerank"}]})
    if saved.status_code in (400, 502) and saved.json().get("data", {}).get("reason") in ("provider_refused", "provider_unreachable"):
        model = "cohere/rerank-v3.5"
        STATE["rerank_requests"] += 1
        saved = call(client, "PUT", "/api/v1/providers", owner.token,
            {"provider": "OpenRouter", "models": [{"name": model, "type": "rerank"}]})
    assert saved.status_code == 200 and saved.json()["code"] == 0, "bounded provider rerank connection test failed"
    # Do not exceed the two-request ceiling when a refusal already consumed the fallback allowance.
    assert STATE["rerank_requests"] < 2, "fallback save consumed the second request; route proof requires a revised budget (not silently exceeded)"
    STATE["rerank_requests"] += 1
    result = request(client, owner, "POST", "/api/v1/datasets/search", {"dataset_ids": [world.dataset_id], "question": FACTS[0].question,
        "rerank_id": f"{model}@OpenRouter", "similarity_threshold": 0, "vector_similarity_weight": 0.3, "size": 6})
    assert result["rerank_applied"] is True and result["chunks"]
    assert all(0 <= hit["rerank_similarity"] <= 1 for hit in result["chunks"])
    assert STATE["rerank_requests"] <= 2
    STATE["router_model"] = model


def test_budget_has_independent_persisted_count(client, owner, world, live_env, started_at):
    persisted = 0
    for chat_id, session_id in STATE["sessions"]:
        rows = sql("SELECT `message` FROM `conversation` WHERE `id` = %s AND `dialog_id` = %s", (session_id, chat_id))
        assert len(rows) == 1
        messages = json.loads(rows[0][0]) if isinstance(rows[0][0], str) else rows[0][0]
        persisted += sum(message.get("role") == "assistant" and bool(message.get("usage")) and not message.get("empty", False) for message in messages)
    assert persisted == STATE["turns"] == 8
    assert persisted + 1 <= CHAT_TURN_CAP  # also include the provider-save connection test
    query = usage_count("app", started_at, owner.tenant_id, live_env.embed_model) - STATE["app_before"]
    assert 12 <= query <= QUERY_EMBED_CAP
    worker = usage_count("task-executor", started_at, owner.tenant_id, live_env.embed_model)
    assert worker == STATE["worker_before"]
    STATE["query_embeddings"] = query
    print("LIVE-CHAT-EVIDENCE", json.dumps({"chat_turns": persisted, "provider_save_chat": 1, "query_embeddings": query,
        "ingestion_embedding_calls": worker, "ingested_chunks": world.chunks, "correct_citations": sum(STATE["citations"]),
        "rerank_requests_including_save": STATE["rerank_requests"], "router_model": STATE.get("router_model"), "chat_model": live_env.chat_model}))


def test_key_never_in_responses_frames_or_logs(live_env, recorder, started_at, world):
    captured = "\n".join(recorder.captured)
    # Nginx is supervised inside app, not a separate Compose service; its stdout is in the app log.
    app_log = logs("app", started_at)
    assert '"POST /api/v1/chat/completions HTTP/' in app_log
    captured += app_log + logs("task-executor", started_at)
    assert leaks(captured, live_env.key) == 0
    assert "sk-or-" not in captured
