"""Original Plan 21 keyword/question enrichment contracts."""
import pytest
from pydantic import ValidationError
from api.db.services.parser_config import ParserConfig
from rag.chunking.types import Chunk
from rag.svr.chunk_doc import build_row
from rag.svr.enrichment import EnrichedFeatures, enrichment_completion, parse_enrichment
from rag.svr.failure import TaskFailure
import json

pytestmark = pytest.mark.unit


def test_question_count_is_bounded_and_defaults_off():
    assert ParserConfig().auto_keywords == 0
    assert ParserConfig().auto_questions == 0
    assert ParserConfig.model_validate({"auto_questions":16}).auto_questions == 16
    with pytest.raises(ValidationError):
        ParserConfig.model_validate({"auto_questions":17})


def test_generated_terms_are_retrieval_fields_without_rewriting_source():
    chunk = Chunk("The east lighthouse is 52 metres high.", (), {}, 9, 0)
    row = build_row(chunk, index=0, doc_id="a"*32, kb_id="b"*32, doc_name="source.txt", task_id="c"*32,
                    from_page=0, to_page=1000000, vector=[1.0], enabled=True,
                    keywords=("beacon altitude",), questions=("How high is the east lighthouse?",))
    assert row["content_with_weight"] == chunk.text
    assert row["important_kwd"] == ["beacon altitude"]
    assert "beacon" in row["important_tks"]
    assert "lighthouse" in row["question_tks"]


def test_one_bounded_response_deduplicates_and_preserves_exact_chunk_order(repo_root):
    source = (repo_root / "test/fixtures/phase6/enrichment-original.txt").read_text()
    assert "52 metres" in source and "73 units" in source and "beacon altitude" not in source
    class Bundle:
        context_tokens = 8192
        calls = []
        def chat(self, system, messages, options):
            self.calls.append((system, messages, options))
            return json.dumps({"items":[{"index":0,"keywords":["beacon altitude","BEACON ALTITUDE"],
                                         "questions":["How high is the east lighthouse?"]}]})
    bundle = Bundle()
    result = enrichment_completion(bundle, [source], 4, 2)
    assert result == (EnrichedFeatures(("beacon altitude",), ("How high is the east lighthouse?",)),)
    assert len(bundle.calls) == 1 and bundle.calls[0][2]["max_tokens"] == 4096
    assert "untrusted data" in bundle.calls[0][0]
    assert json.loads(bundle.calls[0][1][0]["content"])["chunks"][0]["text"] == source


@pytest.mark.parametrize("bad", [
    "not json", "{}", json.dumps({"items":[]}),
    json.dumps({"items":[{"index":1,"keywords":[],"questions":[]}]}),
    json.dumps({"items":[{"index":0,"keywords":["x"],"questions":[],"extra":1}]}),
    json.dumps({"items":[{"index":0,"keywords":[],"questions":["invented"]}]}),
])
def test_malformed_or_over_limit_response_refuses_without_repair(bad):
    with pytest.raises(TaskFailure) as err:
        parse_enrichment(bad, 1, 1, 0)
    assert err.value.code == "provider_refused"


def test_context_and_input_caps_refuse_before_a_model_submission():
    from rag.chunking.errors import ChunkTooLong
    from rag.parsers.errors import FileTooLarge
    class Small:
        context_tokens = 64
        def chat(self, *args):
            pytest.fail("No provider call may be made")
    with pytest.raises(ChunkTooLong):
        enrichment_completion(Small(), ["52 metres"], 1, 0)
    with pytest.raises(FileTooLarge):
        enrichment_completion(Small(), ["x" * 33000], 1, 0)


def test_cancelled_enrichment_never_submits_after_limiter_wait(monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace
    from rag.svr.embedding import EmbedRunner
    from rag.svr.control import TaskCancelled, TaskControl

    entered, release, exited = threading.Event(), threading.Event(), threading.Event()
    closed, calls = [], []
    class Gate:
        def __enter__(self):
            entered.set()
            assert release.wait(5)
        def __exit__(self, *args):
            exited.set()
    settings = SimpleNamespace(ingest=SimpleNamespace(embed_concurrency=1), llm=SimpleNamespace(max_retries=3, chat_timeout_seconds=60))
    runner = EmbedRunner(settings, SimpleNamespace(embed_limiter=Gate()))
    monkeypatch.setattr("rag.svr.embedding.release_database_connection", lambda:closed.append(threading.current_thread().name))
    monkeypatch.setattr("rag.svr.embedding.LLMBundle", lambda *a, **kw:calls.append(a))
    control = TaskControl()
    try:
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="test-enrich-caller") as caller:
            future = caller.submit(runner.enrich, ["52 metres"], "model", 1, 0, SimpleNamespace(tenant_id="tenant"), control)
            assert entered.wait(5)
            control.cancel.set()
            with pytest.raises(TaskCancelled):
                future.result(timeout=3)
            release.set()
            assert exited.wait(5)
        assert not calls
        assert any(name.startswith("test-enrich-caller") for name in closed)
    finally:
        release.set()
        runner.close()
