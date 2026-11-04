"""Optional PDF backend selection must be finite and backed by distinct adapters."""
import hashlib
import io
import json
import zipfile
from pathlib import Path

import httpx
import pytest

from api.db.services.parser_config import validate_parser_config
from api.db.services.service_errors import ServiceError
from rag.parsers.backend_registry import BackendEndpoint, BackendUnavailable
from rag.parsers.backends import docling, mineru

pytestmark = pytest.mark.unit


def test_docling_and_mineru_have_distinct_backend_modules(repo_root: Path) -> None:
    for name in ("docling", "mineru"):
        assert (repo_root / "rag/parsers/backends" / f"{name}.py").is_file(), f"{name} has no backend adapter"


@pytest.mark.parametrize("name", ["docling", "mineru"])
def test_named_pdf_backend_selection_is_explicit(name: str) -> None:
    assert validate_parser_config({"layout_recognize": name})["layout_recognize"] == name


@pytest.mark.parametrize("bad", ["http://operator.example/parse", "../docling", "mineru/../../source", "unknown"])
def test_arbitrary_backend_names_or_urls_are_refused(bad: str) -> None:
    with pytest.raises(ServiceError) as error:
        validate_parser_config({"layout_recognize": bad})
    assert error.value.data == {"field": "layout_recognize"}


DOCLING_RESPONSE = {
    "status": "success",
    "document": {"json_content": {
        "body": {"children": [{"$ref": "#/texts/0"}, {"$ref": "#/tables/0"}]},
        "texts": [{"text": "Lighthouse 52", "label": "section_header", "prov": [{"page_no": 1,
                   "bbox": {"l": 40, "t": 180, "r": 180, "b": 140, "coord_origin": "BOTTOMLEFT"}}]}],
        "tables": [{"data": {"table_cells": [{"text": "Owner"}, {"text": "73"}]},
                    "prov": [{"page_no": 1, "bbox": {"l": 40, "t": 90, "r": 200, "b": 30,
                                                        "coord_origin": "BOTTOMLEFT"}}]}],
    }},
}

MINERU_ITEMS = [
    {"page_idx": 0, "type": "text", "text_level": 1, "text": "Lighthouse 52", "bbox": [100, 100, 450, 300]},
    {"page_idx": 0, "type": "table", "table_body": "Owner | 73", "bbox": [100, 500, 500, 800]},
]
MINERU_RESPONSE = {"backend": "pipeline", "version": "2.5.4", "results": {"source.pdf": {"content_list": json.dumps(MINERU_ITEMS)}}}

MINERU_V4_RESPONSE = {
    "metadata": {"producer": {"name": "mineru", "version": "4.1.6"}},
    "extensions": {"mineru": {"tier": "basic"}},
    "pages": [{"page_idx": 0, "blocks": [
        {"type": "paragraph_title", "content": "Lighthouse 52", "bbox": [0.1, 0.1, 0.45, 0.3]},
        {"type": "table", "content": "Owner | 73", "bbox": [0.1, 0.5, 0.5, 0.8]},
    ]}],
}


def _mineru_v4_zip(document: dict, *, extra_name: str | None = None) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("structured_content.json", json.dumps(document))
        if extra_name:
            archive.writestr(extra_name, b"untrusted")
    return output.getvalue()


def test_docling_bottom_left_and_table_provenance_are_converted_once() -> None:
    blocks = docling.normalize(DOCLING_RESPONSE, {1: (400, 200)}, {1})
    assert [(block.kind, block.text) for block in blocks] == [("heading", "Lighthouse 52"), ("table", "Owner\n73")]
    assert [(box.page, box.x0, box.top, box.x1, box.bottom) for block in blocks for box in block.boxes] == [
        (1, 40, 20, 180, 60), (1, 40, 110, 200, 170)]


def test_docling_recorded_local_service_response_keeps_title_table_and_boxes() -> None:
    fixtures = Path(__file__).parents[1] / "fixtures/phase6"
    annotation = json.loads((fixtures / "docling-real-annotation.json").read_text())
    source = (fixtures / "docling-real-original.pdf").read_bytes()
    response = (fixtures / "docling-real-response.json").read_bytes()
    assert hashlib.sha256(source).hexdigest() == annotation["source_sha256"]
    assert hashlib.sha256(response).hexdigest() == annotation["response_sha256"]
    assert annotation["capture_kind"] == "real_local_service_response"

    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=response, headers={"content-type": "application/json"}))
    blocks = docling.parse(source, BackendEndpoint("http://127.0.0.1:5001", "1.38.2"),
                           {1: (600, 400)}, {1}, transport=transport)
    assert [block.kind for block in blocks] == ["heading", "text", "table"]
    assert blocks[0].text == annotation["expected_title"]
    assert blocks[2].text.splitlines() == annotation["expected_table_cells"]
    assert all(block.boxes and all(box.page == 1 for box in block.boxes) for block in blocks)
    title_box, table_box = blocks[0].boxes[0], blocks[2].boxes[0]
    assert (round(title_box.x0, 2), round(title_box.top, 2)) == (60, 37.08)
    assert (round(table_box.x0, 2), round(table_box.top, 2), round(table_box.x1, 2), round(table_box.bottom, 2)) == (
        58.66, 108.72, 540.85, 300.62,
    )


def test_mineru_thousand_unit_coordinates_are_converted_once() -> None:
    blocks = mineru.normalize(MINERU_RESPONSE, {1: (400, 200)}, {1})
    assert [(block.kind, block.text) for block in blocks] == [("heading", "Lighthouse 52"), ("table", "Owner | 73")]
    assert [(box.x0, box.top, box.x1, box.bottom) for block in blocks for box in block.boxes] == [
        (40, 20, 180, 60), (40, 100, 200, 160)]


def test_mineru_v4_wrapper_returns_structured_cpu_blocks_without_legacy_json(monkeypatch) -> None:
    from rag.parsers.backend_registry import configured_endpoint

    monkeypatch.setenv("PDF_BACKEND_MINERU_URL", "https://approved.example")
    monkeypatch.setenv("PDF_BACKEND_MINERU_VERSION", "4.1.6")
    endpoint = configured_endpoint("mineru")
    seen = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.url.path == "/v1/file_parse"
        assert b'name="file"' in request.content
        assert b'name="tier"' in request.content and b"basic" in request.content
        assert b'name="output_formats"' in request.content and b"default" in request.content
        return httpx.Response(200, content=_mineru_v4_zip(MINERU_V4_RESPONSE), headers={"content-type": "application/zip"})

    blocks = mineru.parse(b"%PDF-1.4 fixture", endpoint, {1: (400, 200)}, {1}, transport=httpx.MockTransport(respond))
    assert [(block.kind, block.text) for block in blocks] == [("heading", "Lighthouse 52"), ("table", "Owner | 73")]
    assert [(box.x0, box.top, box.x1, box.bottom) for block in blocks for box in block.boxes] == [
        (40, 20, 180, 60), (40, 100, 200, 160)]
    assert len(seen) == 1


def test_mineru_v4_recorded_local_service_response_preserves_source_facts() -> None:
    fixtures = Path(__file__).parents[1] / "fixtures/phase6"
    annotation = json.loads((fixtures / "mineru416-real-annotation.json").read_text())
    content = (fixtures / "mineru416-real-original.pdf").read_bytes()
    archive = (fixtures / "mineru416-real-response.zip").read_bytes()
    assert hashlib.sha256(content).hexdigest() == annotation["source_sha256"]
    assert hashlib.sha256(archive).hexdigest() == annotation["response_sha256"]
    assert annotation["capture_kind"] == "real_local_service_response"

    endpoint = BackendEndpoint("http://127.0.0.1:18003", "4.1.6")
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=archive, headers={"content-type": "application/zip"})
    )
    blocks = mineru.parse(content, endpoint, {1: (400, 200)}, {1}, transport=transport)
    assert [block.text for block in blocks] == annotation["expected_facts"]
    assert [block.kind for block in blocks] == ["text", "text"]
    assert [(box.page, *(round(value, 2) for value in (box.x0, box.top, box.x1, box.bottom)))
            for block in blocks for box in block.boxes] == [
        (1, 70, 61.2, 148.4, 75.6), (1, 70, 77.4, 126, 90.6),
    ]


def test_mineru_v4_archive_refuses_traversal_and_invalid_geometry() -> None:
    endpoint = BackendEndpoint("https://approved.example", "4.1.6")
    def respond(body: bytes):
        return httpx.MockTransport(lambda _: httpx.Response(200, content=body, headers={"content-type": "application/zip"}))

    with pytest.raises(BackendUnavailable):
        mineru.parse(b"%PDF-1.4 fixture", endpoint, {1: (400, 200)}, {1},
                     transport=respond(_mineru_v4_zip(MINERU_V4_RESPONSE, extra_name="../escape")))

    invalid = json.loads(json.dumps(MINERU_V4_RESPONSE))
    invalid["pages"][0]["blocks"][0]["bbox"] = [0.1, 0.1, 1.1, 0.3]
    with pytest.raises(BackendUnavailable):
        mineru.parse(b"%PDF-1.4 fixture", endpoint, {1: (400, 200)}, {1},
                     transport=respond(_mineru_v4_zip(invalid)))


def test_mineru_v4_wrapper_wait_and_wrong_version_fail_closed() -> None:
    endpoint = BackendEndpoint("https://approved.example", "4.1.6")
    waiting = httpx.MockTransport(lambda _: httpx.Response(202, json={"status": "running"}))
    with pytest.raises(BackendUnavailable):
        mineru.parse(b"%PDF-1.4 fixture", endpoint, {1: (400, 200)}, {1}, transport=waiting)

    wrong = json.loads(json.dumps(MINERU_V4_RESPONSE))
    wrong["metadata"]["producer"]["version"] = "4.1.5"
    returned = httpx.MockTransport(lambda _: httpx.Response(200, content=_mineru_v4_zip(wrong), headers={"content-type": "application/zip"}))
    with pytest.raises(BackendUnavailable):
        mineru.parse(b"%PDF-1.4 fixture", endpoint, {1: (400, 200)}, {1}, transport=returned)


@pytest.mark.parametrize("adapter,response,path", [
    (docling, DOCLING_RESPONSE, "/v1/convert/file"),
    (mineru, MINERU_RESPONSE, "/file_parse"),
])
def test_service_transport_uses_single_pdf_multipart_and_no_redirect(adapter, response, path) -> None:
    seen = []
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.url.path == path
        assert request.headers["authorization"] == "Bearer operator-token"
        assert b"%PDF-" in request.content
        assert b'source.pdf' in request.content
        return httpx.Response(200, json=response)

    endpoint = BackendEndpoint("https://approved.example", "2.5.4", "operator-token")
    blocks = adapter.parse(b"%PDF-1.4 fixture", endpoint, {1: (400, 200)}, {1}, transport=httpx.MockTransport(handler))
    assert len(blocks) == 2 and len(seen) == 1

    def redirect(_: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://other.example"})
    with pytest.raises(BackendUnavailable):
        adapter.parse(b"%PDF-1.4 fixture", endpoint, {1: (400, 200)}, {1}, transport=httpx.MockTransport(redirect))


def test_invalid_or_remote_geometry_and_zip_are_refused() -> None:
    import copy

    bad_docling = copy.deepcopy(DOCLING_RESPONSE)
    bad_docling["document"]["json_content"]["texts"][0]["prov"][0]["bbox"]["coord_origin"] = "REMOTE"
    with pytest.raises(BackendUnavailable):
        docling.normalize(bad_docling, {1: (400, 200)}, {1})
    bad_mineru = copy.deepcopy(MINERU_RESPONSE)
    invalid_items = copy.deepcopy(MINERU_ITEMS)
    invalid_items[0]["bbox"] = [0, 0, 1001, 500]
    bad_mineru["results"]["source.pdf"]["content_list"] = json.dumps(invalid_items)
    with pytest.raises(BackendUnavailable):
        mineru.normalize(bad_mineru, {1: (400, 200)}, {1})

    def zip_response(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"PK\x03\x04", headers={"content-type": "application/zip"})
    with pytest.raises(BackendUnavailable):
        mineru.parse(b"%PDF-1.4 fixture", BackendEndpoint("https://approved.example", "2.5.4"),
                     {1: (400, 200)}, {1}, transport=httpx.MockTransport(zip_response))


def test_selected_backend_uses_actual_pdf_pages_and_operator_config(monkeypatch) -> None:
    from rag.parsers import backend_registry
    from test.helpers.pdf_files import text_pdf

    content = text_pdf([["Lighthouse 52"]], mediabox=(0, 0, 400, 200))
    seen = []
    monkeypatch.setenv("PDF_BACKEND_DOCLING_URL", "https://approved.example")
    monkeypatch.setenv("PDF_BACKEND_DOCLING_VERSION", "1.0.0")

    def parse(data, endpoint, pages, selected):
        seen.append((data, endpoint.url, pages, selected))
        return docling.normalize(DOCLING_RESPONSE, pages, selected)

    monkeypatch.setattr(docling, "parse", parse)
    result = backend_registry.run_selected("docling", content, {"layout": True, "max_pages": 1, "max_text_bytes": 2048, "backend": "docling"})
    assert seen == [(content, "https://approved.example", {1: (400.0, 200.0)}, {1})]
    assert result["report"] == {"pages_total": 1, "pages_without_text": 0, "layout_backend": "docling", "layout_regions": 2}
    assert result["blocks"][0]["boxes"][0] == {"page": 1, "x0": 40, "top": 20.0, "x1": 180, "bottom": 60.0}


def test_selected_backend_requires_operator_endpoint_and_rejects_submitted_url(monkeypatch) -> None:
    from deepdoc.model_runtime import NativeError
    from rag.parsers.backend_registry import run_selected
    from test.helpers.pdf_files import text_pdf

    monkeypatch.delenv("PDF_BACKEND_DOCLING_URL", raising=False)
    monkeypatch.delenv("PDF_BACKEND_DOCLING_VERSION", raising=False)
    content = text_pdf([["Lighthouse 52"]])
    with pytest.raises(NativeError, match="backend_unavailable"):
        run_selected("docling", content, {"layout": True, "backend": "docling"})
    monkeypatch.setenv("PDF_BACKEND_DOCLING_URL", "https://approved.example")
    monkeypatch.setenv("PDF_BACKEND_DOCLING_VERSION", "1.0.0")
    with pytest.raises(NativeError, match="invalid_options"):
        run_selected("docling", content, {"layout": True, "backend": "docling", "url": "http://untrusted.example"})


def test_mineru_unimplemented_four_zero_schema_is_not_misread_as_legacy_coordinates(monkeypatch) -> None:
    from rag.parsers.backend_registry import configured_endpoint

    monkeypatch.setenv("PDF_BACKEND_MINERU_URL", "https://approved.example")
    monkeypatch.setenv("PDF_BACKEND_MINERU_VERSION", "4.0.0")
    with pytest.raises(BackendUnavailable):
        configured_endpoint("mineru")


@pytest.mark.parametrize("name,payload", [("docling", DOCLING_RESPONSE), ("mineru", MINERU_RESPONSE)])
def test_worker_client_keeps_selected_name_and_source_geometry(tmp_path, name, payload) -> None:
    from common.settings import DeepDocSettings
    from rag.parsers.backend_registry import wire_result
    from rag.parsers.deepdoc_client import DeepDocClient
    from rag.parsers.types import ParseReport, SourceFile

    blocks = (docling if name == "docling" else mineru).normalize(payload, {1: (400, 200)}, {1})
    wire = wire_result(name, blocks, {1: (400, 200)}, 4096)
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.4 fixture")
    seen = []
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/parse"
        seen.append(request.content)
        return httpx.Response(200, json=wire)

    client = DeepDocClient(DeepDocSettings("http://deepdoc.test", "a" * 32), transport=httpx.MockTransport(respond))
    report = ParseReport()
    result = client.parse(SourceFile(source, "pdf", source.stat().st_size), report,
                          page_range=None, limits=None, parser_config={"layout_recognize": name})
    assert result[0].text == "Lighthouse 52"
    assert result[0].boxes[0].top == 20
    assert report.layout_backend == name and report.pages_total == 1
    assert len(seen) == 1 and f'"backend": "{name}"'.encode() in seen[0]


@pytest.mark.asyncio
async def test_authenticated_service_dispatches_selected_backend_without_native_fallback(monkeypatch) -> None:
    import io
    import json

    from werkzeug.datastructures import FileStorage

    from deepdoc.server import create_app
    from rag.parsers import backend_registry

    calls = []
    class Runtime:
        def process_pdf(self, *args):
            calls.append("native")
            raise AssertionError("selected service must not use native fallback")

    def selected(name, content, options):
        calls.append((name, content, options))
        return {"schema_version": 1, "blocks": [], "report": {"pages_total": 1, "pages_without_text": 1,
                "layout_backend": "docling", "layout_regions": 0}}

    monkeypatch.setattr(backend_registry, "run_selected", selected)
    token = "unit-operator-token-for-service"
    app = create_app(Runtime(), token)
    async with app.test_app():
        client = app.test_client()
        options = {"layout": True, "backend": "docling"}
        unauth = await client.post("/v1/parse", files={"file": FileStorage(io.BytesIO(b"%PDF-1.4"), "source.pdf")}, form={"options": json.dumps(options)})
        assert unauth.status_code == 401 and calls == []
        response = await client.post("/v1/parse", headers={"Authorization": f"Bearer {token}"},
                                     files={"file": FileStorage(io.BytesIO(b"%PDF-1.4"), "source.pdf")},
                                     form={"options": json.dumps(options)})
        assert response.status_code == 200
        assert calls == [("docling", b"%PDF-1.4", options)]


@pytest.mark.asyncio
async def test_backend_availability_route_is_authenticated_and_contains_names_only() -> None:
    from api.apps import create_app
    from common.settings import DeepDocSettings
    from test.helpers.app import StubPrincipalResolver, memory_settings

    resolver = StubPrincipalResolver()
    settings = memory_settings(deepdoc=DeepDocSettings(
        url="http://deepdoc:9390", api_token="unit-only-operator-token-000000",
        docling_url="https://docling.example", docling_version="1.0.0",
        mineru_url="https://mineru.example", mineru_version="4.1.6"))
    client = create_app(settings, principal_resolver=resolver).test_client()
    denied = await client.get("/api/v1/parser-backends")
    assert denied.status_code == 401
    allowed = await client.get("/api/v1/parser-backends", headers={"Authorization": f"Bearer {resolver.token}"})
    assert allowed.status_code == 200
    assert (await allowed.get_json())["data"] == {"available": ["deepdoc", "docling", "mineru"]}
    assert "docling.example" not in (await allowed.get_data()).decode()
    assert "mineru.example" not in (await allowed.get_data()).decode()
