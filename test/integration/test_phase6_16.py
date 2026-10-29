"""ASR ownership, actual native refusal boundaries and real timestamp indexing."""

from dataclasses import replace
import io
import wave

import httpx
import pytest

from api.db.services import tenant_model_service as models, tenant_llm_service as credentials
from common.model_ref import ModelRef
from common.settings import DeepDocSettings
from test.conftest import stack_env
from test.integration import test_pipeline_failures as base
from test.helpers.ingest import add_document, add_task, indexed, run_task
from test.helpers.uploads import sql

_bound_database = base._bound_database
registry = base.registry
fake = base.fake
world = base.world
pytestmark = pytest.mark.integration


def configure(world):
    token = stack_env().get("DEEPDOC_API_TOKEN")
    assert token, "Actual native prerequisite missing"
    native = DeepDocSettings(url="http://127.0.0.1:9390", api_token=token)
    world.settings = replace(world.settings, deepdoc=native)
    world.embed_settings = replace(world.embed_settings, deepdoc=native)
    return models.save_instance(world.settings.llm, world.owner.tenant_id, "DeepDoc", "default", api_key=None, api_base=None, api_version=None, models=[models.NewModel("faster-whisper-tiny", "asr", None, 8192)], replace_key=True)


def test_asr_default_capability_and_credential_stay_in_current_workspace(world):
    provider = configure(world)
    model = provider.models[0]
    ref = ModelRef("faster-whisper-tiny", "default", "DeepDoc")
    defaults = models.set_defaults(world.owner.tenant_id, asr=ref)
    assert defaults.asr == model.composite and defaults.embedding
    credential = credentials.get_credential(world.settings.llm, world.owner.tenant_id, ref, "asr")
    assert credential is not None and credential.api_key is None
    assert credentials.get_credential(world.settings.llm, "0" * 32, ref, "asr") is None
    assert credentials.get_credential(world.settings.llm, world.owner.tenant_id, ref, "chat") is None
    models.delete_provider(world.owner.tenant_id, "DeepDoc")
    assert models.get_defaults(world.owner.tenant_id).asr == ""


def test_native_asr_rejects_corruption_silence_and_remote_options_before_inference():
    token = stack_env().get("DEEPDOC_API_TOKEN")
    assert token
    silence = io.BytesIO()
    with wave.open(silence, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(b"\0" * 32000)
    with httpx.Client(base_url="http://127.0.0.1:9390", timeout=10, trust_env=False) as client:
        assert "asr" in client.get("/health").json()["capabilities"]
        assert client.post("/v1/asr", files={"file": ("audio.wav", b"not audio")}).status_code == 401
        for content, error in [(b"not audio", "invalid_audio"), (silence.getvalue(), "no_readable_text")]:
            response = client.post("/v1/asr", headers={"Authorization": "Bearer " + token}, files={"file": ("audio.wav", content)})
            assert response.status_code == 400 and response.json()["error"] == error
        oversized = io.BytesIO()
        with wave.open(oversized, "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(16000)
            stream.writeframes(b"\0" * (32000 * 61))
        response = client.post("/v1/asr", headers={"Authorization": "Bearer " + token}, files={"file": ("audio.wav", oversized.getvalue())})
        assert response.status_code == 413 and response.json()["error"] == "input_too_large"
        response = client.post("/v1/asr", headers={"Authorization": "Bearer " + token}, files={"file": ("audio.wav", b"x")}, data={"options": '{"url":"http://untrusted.invalid"}'})
        assert response.status_code == 400 and response.json()["error"] == "invalid_options"


def test_audio_worker_indexes_actual_seconds_with_test_only_transcript(world, monkeypatch, repo_root):
    configure(world)
    from rag.llm.asr_model import AsrModel
    calls = []

    def transcribe(self, content, language=None):
        calls.append(content)
        return {"schema_version": 1, "duration": 5.38, "language": "en", "segments": [{"start": 0, "end": 2.4, "text": "Lighthouse height fifty two meters."}, {"start": 2.4, "end": 5.38, "text": "Calibration offset seventy three units."}]}

    monkeypatch.setattr(AsrModel, "transcribe", transcribe)
    path = repo_root / "test/fixtures/phase6/audio-original.wav"
    doc = add_document(world, path.name, path.read_bytes())
    sql("UPDATE `document` SET `parser_id`='audio', `parser_config`=%s WHERE `id`=%s", ('{"asr_model":"faster-whisper-tiny@DeepDoc"}', doc))
    result = run_task(world, add_task(doc))
    assert result.chunk_count == 2 and calls == [path.read_bytes()]
    rows = sorted(indexed(world, doc_id=[doc]), key=lambda r: r["order_int"])
    assert [(r["audio_start_flt"], r["audio_end_flt"]) for r in rows] == [(0, 2.4), (2.4, 5.38)]
    assert all(r["position_int"] == [] and r["doc_id"] == doc for r in rows)
    from test.testcases.conftest import BASE_URL
    with httpx.Client(base_url=BASE_URL, timeout=10) as client:
        response = client.get(f"/api/v1/datasets/{world.dataset.id}/documents/{doc}/chunks", headers={"Authorization": "Bearer " + world.owner.token})
        assert response.status_code == 200
        listed = response.json()["data"]["items"]
        assert [row["audio"] for row in listed] == [{"start":0,"end":2.4},{"start":2.4,"end":5.38}]
        assert all(row["positions"] == [] for row in listed)


@pytest.mark.live_model
def test_exact_local_asr_wav_fact_and_timestamp_index(world, repo_root, monkeypatch):
    configure(world)
    from test.helpers.phase6_asr_budget import spend
    from rag.llm.asr_model import AsrModel
    import json
    import time
    original = AsrModel.transcribe
    def measured(self, content, language=None):
        started = time.monotonic()
        value = original(self, content, language)
        (repo_root / "ragflow-logs/phase6-16-wav-result.json").write_text(json.dumps({"native_seconds":time.monotonic()-started,"transcript":value},indent=2)+"\n")
        return value
    monkeypatch.setattr(AsrModel, "transcribe", measured)
    path = repo_root / "test/fixtures/phase6/audio-original.wav"
    doc = add_document(world, path.name, path.read_bytes())
    sql("UPDATE `document` SET `parser_id`='audio', `parser_config`=%s WHERE `id`=%s", ('{"asr_model":"faster-whisper-tiny@DeepDoc","audio_language":"en"}', doc))
    task = add_task(doc)
    spend("wav-worker")
    result = run_task(world, task)
    rows = sorted(indexed(world, doc_id=[doc]), key=lambda r: r["order_int"])
    text = " ".join(r["content_with_weight"] for r in rows).lower()
    assert result.chunk_count == len(rows) > 0
    from test.helpers.phase6_asr_accuracy import assert_audio_facts
    assert_audio_facts(text)
    previous = 0
    for row in rows:
        assert previous <= row["audio_start_flt"] < row["audio_end_flt"] <= 5.38
        assert row["position_int"] == []
        previous = row["audio_end_flt"]


def test_recorded_real_wav_transcript_replays_through_timestamp_index(world, monkeypatch, repo_root):
    import json
    from rag.llm.asr_model import AsrModel
    from test.helpers.phase6_asr_accuracy import assert_audio_facts
    configure(world)
    observed = json.loads((repo_root / ".planning/phases/06-deep-parsing-and-chunking-breadth/06-16-ASR-OBSERVED.json").read_text())
    value = observed["wav"]["transcript"]
    monkeypatch.setattr(AsrModel, "transcribe", lambda *args: value)
    path = repo_root / "test/fixtures/phase6/audio-original.wav"
    doc = add_document(world, path.name, path.read_bytes())
    sql("UPDATE `document` SET `parser_id`='audio', `parser_config`=%s WHERE `id`=%s", ('{"asr_model":"faster-whisper-tiny@DeepDoc"}', doc))
    result = run_task(world, add_task(doc))
    rows = sorted(indexed(world, doc_id=[doc]), key=lambda r: r["order_int"])
    assert result.chunk_count == len(rows) == len(value["segments"])
    assert_audio_facts(" ".join(row["content_with_weight"] for row in rows))
    for row, segment in zip(rows, value["segments"], strict=True):
        assert row["content_with_weight"] == segment["text"]
        assert (row["audio_start_flt"], row["audio_end_flt"]) == (segment["start"], segment["end"])
        assert row["position_int"] == [] and row["doc_id"] == doc
