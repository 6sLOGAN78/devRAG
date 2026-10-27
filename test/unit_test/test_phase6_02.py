"""DeepDoc's authenticated byte protocol, without importing native inference libraries."""

import importlib
from io import BytesIO

import pytest
from werkzeug.datastructures import FileStorage

pytestmark = pytest.mark.unit
TOKEN = "test-only-native-service-token-0001"


@pytest.fixture
def service(repo_root):
    assert (repo_root / "deepdoc/server.py").is_file(), "DeepDoc byte service is not implemented"
    return importlib.import_module("deepdoc.server")


class RecordingOCR:
    def __init__(self):
        self.inputs = []

    def ocr(self, content):
        self.inputs.append(content)
        return {"schema_version": 1, "width": 100, "height": 50,
                "spans": [{"text": "52 meters", "confidence": 0.95, "box": [1, 2, 90, 30]}]}


def upload(content=b"fixture-image", name="page.png"):
    return {"file": FileStorage(stream=BytesIO(content), filename=name, content_type="image/png")}


@pytest.mark.parametrize("authorization", [None, "Bearer invalid", "Basic invalid"])
async def test_ocr_authentication_precedes_input_handling(service, authorization):
    runtime = RecordingOCR()
    app = service.create_app(runtime, TOKEN)
    headers = {"Authorization": authorization} if authorization else {}
    result = await app.test_client().post("/v1/ocr", headers=headers, json={"path": "/etc/passwd"})
    assert result.status_code == 401
    assert runtime.inputs == []
    assert TOKEN not in (await result.get_data()).decode()


async def test_authenticated_ocr_uses_only_uploaded_bytes(service):
    runtime = RecordingOCR()
    app = service.create_app(runtime, TOKEN)
    result = await app.test_client().post("/v1/ocr", headers={"Authorization": f"Bearer {TOKEN}"}, files=upload())
    assert result.status_code == 200
    body = await result.get_json()
    assert body["schema_version"] == 1
    assert body["spans"][0]["text"] == "52 meters"
    assert runtime.inputs == [b"fixture-image"]


@pytest.mark.parametrize("body", [{"path": "/etc/passwd"}, {"url": "http://127.0.0.1/private"}, {}])
async def test_paths_urls_and_nonmultipart_payloads_are_refused(service, body):
    runtime = RecordingOCR()
    app = service.create_app(runtime, TOKEN)
    result = await app.test_client().post("/v1/ocr", headers={"Authorization": f"Bearer {TOKEN}"}, json=body)
    assert result.status_code == 400
    assert runtime.inputs == []


async def test_extra_form_fields_are_refused(service):
    runtime = RecordingOCR()
    app = service.create_app(runtime, TOKEN)
    result = await app.test_client().post("/v1/ocr", headers={"Authorization": f"Bearer {TOKEN}"},
                                          files=upload(), form={"url": "https://example.test/image.png"})
    assert result.status_code == 400
    assert runtime.inputs == []


async def test_upload_limit_refuses_before_inference(service):
    runtime = RecordingOCR()
    app = service.create_app(runtime, TOKEN, max_bytes=10)
    result = await app.test_client().post("/v1/ocr", headers={"Authorization": f"Bearer {TOKEN}"},
                                          files=upload(b"x" * 11))
    assert result.status_code == 413
    assert runtime.inputs == []


async def test_health_is_bounded_and_contains_no_operator_secret(service):
    app = service.create_app(RecordingOCR(), TOKEN)
    result = await app.test_client().get("/health")
    assert result.status_code == 200
    assert await result.get_json() == {"schema_version": 1, "status": "ready", "capabilities": ["ocr"]}
    assert TOKEN not in (await result.get_data()).decode()


def test_service_refuses_missing_operator_secret(service):
    with pytest.raises(ValueError, match="operator token"):
        service.create_app(RecordingOCR(), "")


def test_ctc_blanks_separate_repeated_characters():
    from deepdoc.ocr import decode_ctc

    text, score = decode_ctc([1, 1, 0, 1, 2], [0.9] * 5, ["", "5", "2"])
    assert text == "552" and score == pytest.approx(0.9)


def test_word_segmentation_uses_ink_gaps_not_expected_text():
    from deepdoc.ocr import word_spans

    assert word_spans([], 20) == []
    assert word_spans([1, 2, 4, 6, 20, 21, 24], 20) == [(1, 7), (20, 25)]
    assert word_spans([1, 2, 4, 6, 8], 20) == [(1, 9)]


def test_corrupt_or_missing_model_is_refused_without_native_imports(tmp_path):
    import hashlib

    from deepdoc.model_runtime import NativeError, verify_file

    digest = hashlib.sha256(b"approved").hexdigest()
    target = tmp_path / "model.onnx"
    with pytest.raises(NativeError, match="model_unavailable"):
        verify_file(target, digest, 8)
    target.write_bytes(b"corrupt!")
    with pytest.raises(NativeError, match="model_unavailable"):
        verify_file(target, digest, 8)
    target.write_bytes(b"approved")
    verify_file(target, digest, 8)


@pytest.mark.parametrize("corruption", ["nan", "out_of_bounds", "bad_text", "bad_shape"])
async def test_invalid_native_results_are_refused(service, corruption):
    runtime = RecordingOCR()
    result = runtime.ocr(b"unused")
    runtime.inputs.clear()
    if corruption == "nan":
        result["spans"][0]["confidence"] = float("nan")
    elif corruption == "out_of_bounds":
        result["spans"][0]["box"] = [1, 2, 101, 30]
    elif corruption == "bad_text":
        result["spans"][0]["text"] = "x" * 8193
    else:
        result["spans"] = None
    runtime.ocr = lambda content: result
    response = await service.create_app(runtime, TOKEN).test_client().post(
        "/v1/ocr", headers={"Authorization": f"Bearer {TOKEN}"}, files=upload()
    )
    assert response.status_code == 502
    assert (await response.get_json())["error"] == "invalid_native_result"


def test_native_config_precedence_and_secret_redaction(tmp_path, repo_root):
    from common.settings import load_settings
    from scripts.render_conf import render
    from test.unit_test.test_settings import SECRETS

    values = {**SECRETS, "DEEPDOC_URL": "http://deepdoc:9390", "TENSORRT_DLA_SVR": "http://older:9390",
              "DEEPDOC_API_TOKEN": TOKEN}
    config = tmp_path / "service.yaml"
    config.write_text(render((repo_root / "conf/service_conf.yaml.template").read_text(), values))
    settings = load_settings(config)
    assert settings.deepdoc.url == "http://deepdoc:9390"
    assert settings.deepdoc.api_token == TOKEN
    assert TOKEN not in repr(settings) and TOKEN not in repr(settings.deepdoc)


def test_native_config_alias_and_absent_defaults(tmp_path, repo_root):
    from common.settings import load_settings
    from scripts.render_conf import render
    from test.unit_test.test_settings import SECRETS

    config = tmp_path / "service.yaml"
    template = (repo_root / "conf/service_conf.yaml.template").read_text()
    config.write_text(render(template, {**SECRETS, "TENSORRT_DLA_SVR": "http://alias:9390", "DEEPDOC_API_TOKEN": TOKEN}))
    assert load_settings(config).deepdoc.url == "http://alias:9390"
    config.write_text(render(template, SECRETS))
    assert load_settings(config).deepdoc.url == ""


def test_all_provisioned_models_are_verified_before_readiness(monkeypatch, tmp_path):
    import deepdoc.model_runtime as module

    checked = []
    monkeypatch.setattr(module, "verify_file", lambda path, digest, size: checked.append(path.name))
    monkeypatch.setattr(module.ModelRuntime, "session", lambda self, name: None)
    (tmp_path / "ocr.res").write_text("A\nB\n")
    module.ModelRuntime(tmp_path)
    assert set(checked) == {"det.onnx", "rec.onnx", "ocr.res", "layout.onnx", "tsr.onnx"}


async def test_timed_out_native_call_keeps_the_single_slot_until_it_finishes(service):
    import threading

    release = threading.Event()

    class HeldOCR(RecordingOCR):
        def ocr(self, content):
            assert release.wait(2), "test native call was not released"
            return super().ocr(content)

    runtime = HeldOCR()
    app = service.create_app(runtime, TOKEN, deadline=0.01)
    try:
        client = app.test_client()
        first = await client.post("/v1/ocr", headers={"Authorization": f"Bearer {TOKEN}"}, files=upload())
        assert first.status_code == 504
        second = await client.post("/v1/ocr", headers={"Authorization": f"Bearer {TOKEN}"}, files=upload())
        assert second.status_code == 503 and (await second.get_json())["error"] == "busy"
    finally:
        release.set()


@pytest.mark.parametrize("url", ["file:///models", "http://user:pass@deepdoc:9390", "https://deepdoc/path", "http://deepdoc?key=secret"])
def test_native_operator_url_refuses_credentials_paths_and_nonhttp(tmp_path, repo_root, url):
    from common.settings import ConfigError, load_settings
    from scripts.render_conf import render
    from test.unit_test.test_settings import SECRETS

    config = tmp_path / "service.yaml"
    config.write_text(render((repo_root / "conf/service_conf.yaml.template").read_text(),
                             {**SECRETS, "DEEPDOC_URL": url, "DEEPDOC_API_TOKEN": TOKEN}))
    with pytest.raises(ConfigError, match="deepdoc.url"):
        load_settings(config)
