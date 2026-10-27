"""Canonical layout semantics, exact overlap boundary and deterministic reading order."""

import importlib

import pytest

from deepdoc.model_runtime import NativeError
from rag.parsers.types import PageBox, ParsedBlock

pytestmark = pytest.mark.unit


def geometry():
    assert importlib.util.find_spec("deepdoc.geometry") is not None, "layout geometry implementation is missing"
    return importlib.import_module("deepdoc.geometry")


def block(text, x=10, y=10):
    return ParsedBlock(text, boxes=(PageBox(1, x, y, x + 100, y + 10),), page_sizes={1: (600, 800)})


def test_runtime_advertises_layout_only_with_implemented_native_path():
    from deepdoc.native_runtime import NativeRuntime

    assert "layout" in NativeRuntime.capabilities


def test_all_eleven_documented_labels_have_distinct_canonical_ids():
    assert geometry().LABELS == ("_background_", "Text", "Title", "Figure", "Figure caption", "Table", "Table caption", "Header", "Footer", "Reference", "Equation")


@pytest.mark.parametrize("fraction,kind", [(0.3999, "text"), (0.4, "heading")])
def test_intersection_over_text_area_exact_boundary(fraction, kind):
    g = geometry()
    region = g.Region(2, 0.9, (10, 10, 10 + 100 * fraction, 20))
    result = g.apply_layout([block("PLANTED")], [region])
    assert result[0].kind == kind


def test_header_footer_removed_reference_preserved_and_semantics_carried():
    g = geometry()
    blocks = [block("HEADER", y=0), block("REFERENCE", y=40), block("FIGURE", y=80), block("FOOTER", y=780)]
    regions = [g.Region(label, 0.9, (b.boxes[0].x0, b.boxes[0].top, b.boxes[0].x1, b.boxes[0].bottom)) for label, b in zip((7, 9, 3, 8), blocks)]
    result = g.apply_layout(blocks, regions)
    assert [b.text for b in result] == ["REFERENCE", "FIGURE"]
    assert [b.layout_label for b in result] == ["Reference", "Figure"]
    assert result[1].kind == "text"


def test_two_column_order_is_column_major_and_stable_with_ties():
    g = geometry()
    a, b, c, d = block("ALPHA", 10, 100), block("BRAVO", 10, 200), block("CHARLIE", 330, 100), block("DELTA", 330, 200)
    regions = [g.Region(1, 0.9, (5, 95, 115, 215)), g.Region(1, 0.9, (325, 95, 435, 215))]
    for incoming in ([a, c, b, d], [d, b, c, a]):
        assert [b.text for b in g.apply_layout(incoming, regions)] == ["ALPHA", "BRAVO", "CHARLIE", "DELTA"]


def test_nms_is_class_aware_and_score_ties_are_deterministic():
    g = geometry()
    a, b, c = g.Region(1, 0.8, (0, 0, 100, 100)), g.Region(1, 0.8, (1, 1, 101, 101)), g.Region(2, 0.8, (0, 0, 100, 100))
    assert g.nms([b, c, a], 0.45) == g.nms([a, b, c], 0.45) == [a, c]


@pytest.mark.parametrize("box", [(0, 0, float("nan"), 10), (-1, 0, -1, 10), (10, 0, 1, 10)])
def test_invalid_regions_are_typed_refusals(box):
    g = geometry()
    with pytest.raises(NativeError):
        g.Region(1, 0.9, box)


def test_unknown_canonical_label_refused_and_empty_pages_valid():
    g = geometry()
    with pytest.raises(NativeError):
        g.Region(11, 0.9, (0, 0, 10, 10))
    assert g.apply_layout([], []) == []


def test_approved_model_label_adapter_does_not_confuse_canonical_ids():
    assert importlib.util.find_spec("deepdoc.layout") is not None, "model layout adapter is missing"
    layout = importlib.import_module("deepdoc.layout")
    assert layout.semantic_id(0, (0, 100, 10, 110), 800) == 2
    assert layout.semantic_id(1, (0, 100, 10, 110), 800) == 1
    assert layout.semantic_id(2, (0, 0, 10, 10), 800) == 7
    assert layout.semantic_id(2, (0, 790, 10, 800), 800) == 8
    assert layout.semantic_id(2, (0, 300, 10, 310), 800) == 9
    with pytest.raises(NativeError):
        layout.semantic_id(10, (0, 100, 10, 110), 800)


def test_layout_operation_metadata_survives_rollup_without_user_progress_leak():
    from types import SimpleNamespace

    from rag.svr.progress import _counts_dsl, _summarise

    summary = _summarise([SimpleNamespace(progress=1, retry_count=1, progress_msg="[pages] total=1 without_text=0\n[layout] backend=deepdoc-onnx regions=5")])
    data = _counts_dsl(summary, 4)
    assert data.get("layout_backend") == "deepdoc-onnx" and data.get("layout_regions") == 5
    assert not any("[layout]" in line for line in summary.lines)


def test_saved_layout_selection_reaches_remote_request_and_returns_typed_metadata(tmp_path):

    import httpx

    from common.settings import DeepDocSettings
    from rag.parsers.deepdoc_client import DeepDocClient, NativeUnavailable
    from rag.parsers.types import ParseReport, SourceFile

    path = tmp_path / "source.pdf"
    path.write_bytes(b"%PDF-placeholder")

    def respond(request):
        assert b'"layout": true' in request.read()
        return httpx.Response(200, json={"schema_version": 1, "blocks": [], "report": {"pages_total": 1, "pages_without_text": 1, "layout_backend": "deepdoc-onnx", "layout_regions": 0}})

    client = DeepDocClient(DeepDocSettings(url="http://native.test", api_token="a" * 32), transport=httpx.MockTransport(respond))
    report = ParseReport()
    assert client.parse(SourceFile(path, "pdf", path.stat().st_size), report, page_range=(0, 1), limits=None, parser_config={"layout_recognize": True}) == []
    assert report.layout_backend == "deepdoc-onnx"
    with pytest.raises(NativeUnavailable):
        client.parse(SourceFile(path, "pdf", path.stat().st_size), report, page_range=(0, 1), limits=None, parser_config={"layout_recognize": "docling"})


def test_ambiguous_margin_detection_keeps_source_without_independent_body_region():
    from deepdoc.layout import semantic_id

    assert semantic_id(2, (0, 0, 10, 10), 800, has_body=False) == 9


def test_many_wide_headings_do_not_exhaust_python_recursion():
    from dataclasses import replace

    g = geometry()
    blocks = [replace(block(str(i), 10, i / 2), kind="heading") for i in range(1100)]
    result = g.apply_layout(blocks, [])
    assert len(result) == 1100 and result[0].text == "0" and result[-1].text == "1099"
