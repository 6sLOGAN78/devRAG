"""Vision capability contracts precede driver, parser and credential implementation."""

import importlib.util
import pytest
from rag.llm import resolve_provider
from api.db.services import tenant_model_service as models

pytestmark = pytest.mark.unit


def test_vision_registry_and_existing_capability_flags_remain_distinct():
    assert models.TYPE_BITS.get("vision") == 8, "Vision capability is missing"
    assert models.TYPE_BITS["chat"] == 1 and models.TYPE_BITS["embedding"] == 2 and models.TYPE_BITS["rerank"] == 16
    assert "vision" in resolve_provider("OpenRouter").model_types
    assert "vision" in resolve_provider("OpenAI-API-Compatible").model_types


def test_same_name_chat_and_vision_are_distinct_requests_and_identical_pair_refuses():
    from api.db.services.service_errors import ServiceError

    pair = [models.NewModel("shared-model", "chat", None, 8192), models.NewModel("shared-model", "vision", None, 8192)]
    try:
        models._check_models("OpenRouter", "default", pair)
    except ServiceError:
        pytest.fail("Same-name distinct chat and vision capability requests must be accepted")
    with pytest.raises(ServiceError):
        models._check_models("OpenRouter", "default", [pair[0], pair[0]])


def test_picture_parser_and_chunker_are_real_and_lazy():
    from rag.parsers.router import parser_for_suffix, parseable
    from rag.chunking.factory import available

    assert parseable("png"), "Picture parser is missing"
    assert parser_for_suffix("png").name == "image"
    assert available("picture"), "Picture chunker is missing"
    assert importlib.util.find_spec("rag.llm.vision_model") is not None, "Vision operation is missing"


def test_vision_sends_only_bounded_data_url_with_fixed_untrusted_image_prompt(monkeypatch, repo_root):
    from rag.llm.vision_model import VisionBase, CAPTION_SYSTEM
    from rag.llm.chat_model import LiteLLMBase
    from rag.llm.errors import ModelException

    calls = []

    def chat(self, system, history, conf):
        calls.append((system, history, conf))
        return "A lighthouse with a red roof and label 52 metres.", 19

    monkeypatch.setattr(LiteLLMBase, "chat", chat)
    driver = object.__new__(VisionBase)
    image = (repo_root / "test/fixtures/phase6/picture-original.png").read_bytes()
    assert driver.describe(image)[1] == 19
    system, history, conf = calls[0]
    assert system == CAPTION_SYSTEM and "untrusted" in system
    url = history[0]["content"][1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,") and conf == {"max_tokens": 256, "temperature": 0}
    for bad in ["https://example.invalid/image.png", b"not-png", b"\x89PNG\r\n\x1a\n" + b"x" * (4 * 1024 * 1024)]:
        with pytest.raises(ModelException):
            driver.describe(bad)
    assert len(calls) == 1


def test_empty_vision_answer_refuses_without_fictional_caption(monkeypatch, repo_root):
    from rag.llm.vision_model import VisionBase
    from rag.llm.chat_model import LiteLLMBase
    from rag.llm.errors import ModelException

    monkeypatch.setattr(LiteLLMBase, "chat", lambda *args: (" ", 0))
    with pytest.raises(ModelException):
        object.__new__(VisionBase).describe((repo_root / "test/fixtures/phase6/picture-original.png").read_bytes())


def test_cancel_while_waiting_provider_slot_never_starts_vision_call(monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from contextlib import contextmanager
    from types import SimpleNamespace
    from rag.svr.embedding import EmbedRunner
    from rag.svr.control import TaskControl, TaskCancelled

    entered = threading.Event()
    release = threading.Event()
    exited = threading.Event()
    calls = []

    class Gate:
        def __enter__(self):
            entered.set()
            assert release.wait(5)

        def __exit__(self, *args):
            exited.set()

    runner = EmbedRunner(SimpleNamespace(ingest=SimpleNamespace(embed_concurrency=1)), SimpleNamespace(embed_limiter=Gate()))
    monkeypatch.setattr("rag.svr.embedding.release_database_connection", lambda: None)
    monkeypatch.setattr("rag.svr.embedding.LLMBundle", lambda *a, **kw: calls.append(a))
    control = TaskControl()
    try:
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="test-picture-caller") as caller:
            future = caller.submit(runner.describe_image, b"pixels", "model", SimpleNamespace(tenant_id="tenant"), control)
            assert entered.wait(5)
            control.cancel.set()
            with pytest.raises(TaskCancelled):
                future.result(timeout=3)
            release.set()
            assert exited.wait(5)
        assert calls == []
    finally:
        release.set()
        runner.close()


def test_same_name_embedding_cannot_inherit_chat_dimension_metadata():
    from api.db.services.service_errors import ServiceError

    pair = [models.NewModel("same", "chat", None, 8192), models.NewModel("same", "embedding", 8, 8192)]
    with pytest.raises(ServiceError):
        models._check_models("OpenAI-API-Compatible", "default", pair)


def test_vision_caption_cannot_reflect_the_sealed_provider_key(monkeypatch):
    from rag.llm.vision_model import VisionBase
    from api.db.services.llm_service import LLMBundle

    driver = object.__new__(VisionBase)
    monkeypatch.setattr(VisionBase, "describe", lambda *args: ("image label and provider-secret-value", 0))
    bundle = object.__new__(LLMBundle)
    bundle._driver = driver
    bundle._scrub = lambda value: value.replace("provider-secret-value", "[hidden]")
    assert bundle.describe(b"pixels") == "image label and [hidden]"
