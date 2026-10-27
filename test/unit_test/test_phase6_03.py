"""Remote PDF boundary: no native imports, correct page selection and typed geometry."""

import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


def test_api_and_worker_pdf_imports_do_not_load_native_pdf_libraries():
    code = ("import sys; import api.db.services.page_service, api.db.services.pdf_pages, rag.svr.pipeline; "
            "assert not any(n in sys.modules for n in ('pypdfium2','onnxruntime','cv2')), 'native PDF imports crossed service boundary'")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False, timeout=30)
    assert result.returncode == 0, result.stderr


def test_page_ranges_partition_only_selected_one_based_pages(monkeypatch):
    from api.db.services import ingestion_service

    monkeypatch.setattr(ingestion_service, "pdf_page_count", lambda *args, **kwargs: 30)
    settings = SimpleNamespace(ingest=SimpleNamespace(task_page_size=12))
    doc = SimpleNamespace(id="a" * 32, suffix="pdf", location="blob", content_hash="hash",
                          parser_config={"pages": [[2, 4], [13, 30]]})
    assert ingestion_service._page_ranges(settings, object(), doc) == [(1, 4), (12, 24), (24, 30)]


def test_overlapping_page_ranges_do_not_duplicate_ingestion(monkeypatch):
    from api.db.services import ingestion_service

    monkeypatch.setattr(ingestion_service, "pdf_page_count", lambda *args, **kwargs: 13)
    settings = SimpleNamespace(ingest=SimpleNamespace(task_page_size=12))
    doc = SimpleNamespace(id="a" * 32, suffix="pdf", location="blob", content_hash="hash",
                          parser_config={"pages": [[1, 8], [4, 13]]})
    assert ingestion_service._page_ranges(settings, object(), doc) == [(0, 12), (12, 13)]


def test_source_payload_fixture_is_original_and_fixed(repo_root):
    annotation = json.loads((repo_root / "test/fixtures/phase6/ocr-planted.json").read_text())
    assert annotation["required_facts"] == ["LIGHTHOUSE", "52", "ORCHARD", "9100"]


def test_layout_configuration_changes_task_digest_without_changing_geometry_inputs():
    from api.db.services.ingestion_service import _digest_for

    document = SimpleNamespace(id="a" * 32, content_hash="hash", parser_id="naive", parser_config={"layout_recognize": False})
    first = _digest_for(document, 0, 12)
    document.parser_config = {"layout_recognize": True}
    assert _digest_for(document, 0, 12) != first


def test_entirely_out_of_range_page_selection_is_refused_before_start(monkeypatch):
    from api.db.services import ingestion_service
    from api.db.services.service_errors import ServiceError

    monkeypatch.setattr(ingestion_service, "pdf_page_count", lambda *args, **kwargs: 3)
    document = SimpleNamespace(id="a" * 32, suffix="pdf", location="blob", content_hash="hash", parser_config={"pages": [[9, 10]]})
    with pytest.raises(ServiceError) as failure:
        ingestion_service._page_ranges(SimpleNamespace(ingest=SimpleNamespace(task_page_size=12)), object(), document)
    assert failure.value.reason == "parser_config_invalid"


def test_missing_local_source_has_typed_remote_boundary_failure(tmp_path):
    from common.settings import DeepDocSettings
    from rag.parsers.deepdoc_client import DeepDocClient, NativeUnavailable

    with pytest.raises(NativeUnavailable):
        DeepDocClient(DeepDocSettings(url="http://native.test", api_token="a" * 32)).document_info(tmp_path / "missing.pdf")


@pytest.mark.parametrize("change", ["schema", "nan", "wrong_page", "kind", "report", "sizes", "json", "outage"])
def test_malformed_or_unavailable_remote_pdf_is_refused_without_local_fallback(tmp_path, change):
    import httpx

    from common.settings import DeepDocSettings
    from rag.parsers.deepdoc_client import DeepDocClient, NativeUnavailable
    from rag.parsers.types import ParseReport, SourceFile

    path = tmp_path / "source.pdf"
    path.write_bytes(b"not a local parseable PDF")
    data = {"schema_version": 1, "report": {"pages_total": 1, "pages_without_text": 0},
            "blocks": [{"text": "ORCHARD 9100", "kind": "text", "boxes": [
                {"page": 2, "x0": 10, "top": 10, "x1": 90, "bottom": 30}], "page_sizes": {"2": [100, 200]}}]}
    if change == "schema":
        data["schema_version"] = True
    elif change == "nan":
        data["blocks"][0]["boxes"][0]["top"] = float("nan")
    elif change == "wrong_page":
        data["blocks"][0]["boxes"][0]["page"] = 1
    elif change == "kind":
        data["blocks"][0]["kind"] = "unknown"
    elif change == "sizes":
        data["blocks"][0]["page_sizes"] = []
    elif change == "report":
        data["report"]["pages_without_text"] = 2

    def respond(request):
        assert request.url.path == "/v1/parse"
        if change == "outage":
            raise httpx.ConnectError("offline", request=request)
        return httpx.Response(200, content=b"not json" if change == "json" else json.dumps(data).encode())

    client = DeepDocClient(DeepDocSettings(url="http://native.test", api_token="a" * 32), transport=httpx.MockTransport(respond))
    with pytest.raises(NativeUnavailable):
        client.parse(SourceFile(path, "pdf", path.stat().st_size), ParseReport(), page_range=(1, 2), limits=None)


def test_native_outage_is_retryable_and_never_cached_as_damaged(monkeypatch):
    from api.db.services import pdf_pages
    from api.db.services.service_errors import Kind, ServiceError
    from rag.parsers.deepdoc_client import NativeUnavailable

    attempts = []

    def count(*args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise NativeUnavailable()
        return 13

    monkeypatch.setattr(pdf_pages, "count_pages", count)
    settings = SimpleNamespace(deepdoc=SimpleNamespace(url="http://remote.test"))
    storage = SimpleNamespace(iter_chunks=lambda *args: iter([b"source bytes"]))
    pdf_pages.clear_cache()
    try:
        with pytest.raises(ServiceError) as error:
            pdf_pages.pdf_page_count(settings, "outage-doc", "blob", "hash", "pdf", storage=storage)
        assert error.value.kind is Kind.UNAVAILABLE and error.value.reason == "parse_unavailable"
        assert pdf_pages.pdf_page_count(settings, "outage-doc", "blob", "hash", "pdf", storage=storage) == 13
        assert attempts == [1, 1]
    finally:
        pdf_pages.clear_cache()
