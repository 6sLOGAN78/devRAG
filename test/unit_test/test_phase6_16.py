"""Audio capability, honest timestamps and native boundary contracts."""

import asyncio
import importlib.util
import io

import pytest
from werkzeug.datastructures import FileStorage

pytestmark = pytest.mark.unit


def test_audio_capability_uses_reserved_bit_and_real_chunker():
    from common.model_capabilities import TYPE_BITS
    from rag.chunking.factory import available
    from rag.parsers.router import parseable
    from rag.llm import resolve_provider

    assert TYPE_BITS.get("asr") == 4, "ASR capability is missing"
    assert TYPE_BITS["vision"] == 8 and TYPE_BITS["rerank"] == 16
    assert available("audio") and parseable("wav") and parseable("mp3")
    assert resolve_provider("DeepDoc").model_types == ("asr",)


def test_audio_segments_are_monotonic_bounded_and_have_no_page_geometry():
    assert importlib.util.find_spec("rag.parsers.audio") is not None, "Audio parser is missing"
    from rag.parsers.audio_segments import AudioSpan, transcript_of
    from rag.parsers.types import ParsedBlock
    from rag.chunking.audio import AudioConfig, chunk

    value = {"schema_version": 1, "duration": 5.38, "language": "en", "segments": [{"start": 0, "end": 2.2, "text": "The lighthouse height is fifty two meters."}, {"start": 2.2, "end": 5.3, "text": "The calibration offset is seventy three units."}]}
    result = transcript_of(value)
    blocks = [ParsedBlock(s["text"], "audio", audio=AudioSpan(s["start"], s["end"])) for s in result["segments"]]
    chunks = list(chunk(blocks, AudioConfig()))
    assert len(chunks) == 2 and chunks[0].audio == AudioSpan(0, 2.2)
    assert "fifty two" in chunks[0].text and "seventy three" in chunks[1].text
    assert all(c.positions == () and not c.page_sizes for c in chunks)
    for start, end in [(float("nan"), 1), (2, 1), (-1, 2), (0, 61), (True, 2)]:
        with pytest.raises(ValueError):
            AudioSpan(start, end)
    with pytest.raises(ValueError):
        transcript_of({**value, "segments": [value["segments"][1], value["segments"][0]]})


def test_asr_native_route_authenticates_bytes_and_rejects_options():
    from deepdoc.server import create_app

    class Runtime:
        def process_asr(self, content, options):
            assert content == b"original-wave" and options == {}
            return {"schema_version": 1, "duration": 2, "language": "en", "segments": [{"start": 0, "end": 2, "text": "Lighthouse fifty two."}]}

    async def check():
        token = "local-test-operator-token-with-no-secret"
        runtime = Runtime()
        app = create_app(runtime, token)
        async with app.test_app():
            client = app.test_client()
            response = await client.post("/v1/asr")
            assert response.status_code == 401
            response = await client.post("/v1/asr", headers={"Authorization": "Bearer " + token}, files={"file": FileStorage(io.BytesIO(b"original-wave"), "speech.wav")})
            assert response.status_code == 200, "Authenticated ASR byte route is missing"
            assert (await response.get_json())["segments"][0]["text"] == "Lighthouse fifty two."
            response = await client.post("/v1/asr", headers={"Authorization": "Bearer " + token}, form={"options": '{"url":"http://untrusted.invalid"}'}, files={"file": FileStorage(io.BytesIO(b"original-wave"), "speech.wav")})
            assert response.status_code == 400
            runtime.process_asr = lambda *args: {"schema_version": 1, "segments": []}
            response = await client.post("/v1/asr", headers={"Authorization": "Bearer " + token}, files={"file": FileStorage(io.BytesIO(b"original-wave"), "speech.wav")})
            assert response.status_code == 502, "Invalid native timestamps must not be published"

    asyncio.run(check())


def test_asr_client_uses_only_operator_service_and_fixed_model():
    from dataclasses import replace
    from common.settings import DeepDocSettings
    from test.helpers.app import memory_settings
    from rag.llm.asr_model import AsrModel
    from rag.parsers.deepdoc_client import NativeUnavailable

    settings = replace(memory_settings(), deepdoc=DeepDocSettings(url="http://deepdoc:9390", api_token="unit-operator-token-for-service"))
    for name, address in [("arbitrary-model", None), ("faster-whisper-tiny", "https://remote.invalid"), ("faster-whisper-tiny", "http://169.254.169.254")]:
        with pytest.raises(NativeUnavailable):
            AsrModel(settings, name, address)
    assert AsrModel(settings, "faster-whisper-tiny").client.settings == settings.deepdoc


def test_audio_index_and_source_views_keep_seconds_without_page_boxes():
    import datetime
    from rag.parsers.audio_segments import AudioSpan
    from rag.chunking.types import Chunk
    from rag.svr.chunk_doc import build_row
    from api.db.services.chunk_view import chunk_view_fields

    value = Chunk("Lighthouse fifty two.", (), {}, 4, 0, audio=AudioSpan(1.2, 3.8))
    row = build_row(value, index=0, doc_id="doc", kb_id="kb", doc_name="speech.wav", task_id="task", from_page=0, to_page=1000000, vector=[1.0, 0.0], enabled=True, now=datetime.datetime(2026, 1, 1))
    assert (row["audio_start_flt"], row["audio_end_flt"]) == (1.2, 3.8)
    assert row["position_int"] == []
    assert chunk_view_fields(row)["audio"] == {"start": 1.2, "end": 3.8}


def test_native_asr_uses_no_vad_download_and_refuses_language_mismatch(monkeypatch):
    from types import SimpleNamespace
    from deepdoc.asr import ASR
    from deepdoc.model_runtime import NativeError

    monkeypatch.setattr("deepdoc.asr.decode_audio", lambda content: [0.1] * 16000)
    calls = []
    def transcribe(audio, **options):
        calls.append(options)
        return iter([SimpleNamespace(start=0, end=1, text="Lighthouse fifty two.", no_speech_prob=0.01)]), SimpleNamespace(language="en")
    driver = object.__new__(ASR)
    driver.model = SimpleNamespace(transcribe=transcribe)
    result = driver.process(b"speech", {})
    assert result["segments"][0]["text"] == "Lighthouse fifty two."
    assert calls == [{"language":None,"beam_size":5,"best_of":1,"temperature":0,"vad_filter":False,"condition_on_previous_text":False,"word_timestamps":False}]
    with pytest.raises(NativeError, match="language_mismatch"):
        driver.process(b"speech", {"language":"zh"})
    with pytest.raises(NativeError, match="invalid_options"):
        driver.process(b"speech", {"url":"http://untrusted.invalid"})


def test_cancelled_asr_waiter_cannot_start_a_native_call(monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace
    from rag.svr.embedding import EmbedRunner
    from rag.svr.control import TaskControl, TaskCancelled

    entered, release, exited = threading.Event(), threading.Event(), threading.Event()
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
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="test-asr-caller") as caller:
            future = caller.submit(runner.transcribe_audio, b"speech", "model", SimpleNamespace(tenant_id="tenant"), control)
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


def test_asr_provision_refuses_a_revision_outside_the_approved_packet(monkeypatch, tmp_path):
    import json
    from scripts import provision_deepdoc

    (tmp_path / "deepdoc").mkdir()
    (tmp_path / "deepdoc/asr-model.json").write_text(json.dumps({"revision":"0" * 40,"files":{}}))
    monkeypatch.setattr(provision_deepdoc, "ROOT", tmp_path)
    target = tmp_path / "must-not-acquire"
    with pytest.raises(ValueError, match="revision differs"):
        provision_deepdoc.provision(target, asr=True)
    assert not target.exists()


def test_retained_real_asr_results_satisfy_the_explicitly_accepted_spelling_scope(repo_root):
    import json
    from rag.parsers.audio_segments import transcript_of, AudioSpan
    from test.helpers.phase6_asr_accuracy import assert_audio_facts

    phase = repo_root / ".planning/phases/06-deep-parsing-and-chunking-breadth"
    approval = json.loads((phase / "06-16-SPELLING-ACCEPTANCE.json").read_text())
    assert approval["status"] == "approved" and approval["human_response"] == "Accept spelling equivalence"
    observed = json.loads((phase / "06-16-ASR-OBSERVED.json").read_text())
    assert len(observed["calls"]) == 3 and observed["paid_external_calls"] == 0
    wav = transcript_of(observed["wav"]["transcript"])
    assert_audio_facts(" ".join(segment["text"] for segment in wav["segments"]))
    chunks = observed["mp3"]["chunks"]
    assert chunks["total"] == len(chunks["items"]) > 0
    assert_audio_facts(" ".join(row["text"] for row in chunks["items"]))
    previous = 0
    for row in chunks["items"]:
        span = AudioSpan(**row["audio"])
        assert previous <= span.start < span.end <= 5.38
        assert row["positions"] == [] and row["origin"] == "parsed"
        previous = span.end
    for bad in ["The light house height is 51 meters and calibration is 73 units.", "The lighthouse height is 52 meters and calibration is 74 units.", "A house is 52 meters and calibration is 73 units.", "The lighthouse height is 152 meters and calibration is 73 units.", "The lighthouse height is 73 meters and calibration is 52 units."]:
        with pytest.raises(AssertionError):
            assert_audio_facts(bad)


def test_retained_asr_spend_cannot_be_reset_by_clearing_local_logs(monkeypatch, tmp_path):
    import json
    from test.helpers.phase6_asr_budget import spend

    phase = tmp_path / ".planning/phases/06-deep-parsing-and-chunking-breadth"
    phase.mkdir(parents=True)
    (phase / "06-16-ASR-OBSERVED.json").write_text(json.dumps({"calls":[{"label":"wav-worker"},{"label":"save-probe"},{"label":"mp3-worker-browser"}]}))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(AssertionError, match="cap exhausted"):
        spend("forbidden-replay")


def test_malformed_native_asr_refusal_is_a_fixed_unavailable_error():
    import httpx
    from common.settings import DeepDocSettings
    from rag.parsers.deepdoc_client import DeepDocClient, NativeUnavailable

    transport = httpx.MockTransport(lambda request: httpx.Response(400, json=[]))
    client = DeepDocClient(DeepDocSettings(url="http://native.invalid", api_token="unit-operator-token-for-service"), transport=transport)
    with pytest.raises(NativeUnavailable):
        client._request("/v1/asr", b"audio", {})
