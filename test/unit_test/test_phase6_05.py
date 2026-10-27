"""Bounded deterministic normalized-image contract and scoped ownership identifiers."""

import importlib

import pytest

from rag.parsers.types import ParsedBlock

pytestmark = pytest.mark.unit


def assets():
    assert importlib.util.find_spec("rag.parsers.assets") is not None, "typed normalized-image contract is missing"
    return importlib.import_module("rag.parsers.assets")


def test_parsed_blocks_carry_typed_defaulted_image_descriptors():
    assert "assets" in ParsedBlock.__dataclass_fields__, "extracted images cannot reach the pipeline"
    assert ParsedBlock("unchanged").assets == ()


def test_normalized_asset_round_trip_checks_actual_digest(repo_root):
    a = assets()
    raw = (repo_root / "test/fixtures/phase6/ocr-planted.png").read_bytes()
    asset = a.ParsedAsset.from_png(raw, width=1400, height=400, caption="<b>literal caption</b>")
    restored = a.decode_asset(a.encode_asset(asset))
    assert restored == asset and restored.content == raw
    assert len(asset.sha256) == 64 and asset.mime_type == "image/png"
    bad = a.encode_asset(asset)
    bad["sha256"] = "0" * 64
    with pytest.raises(a.InvalidAsset):
        a.decode_asset(bad)


def test_asset_keys_are_owned_scoped_and_never_caller_paths():
    a = assets()
    first = a.asset_object_key("a" * 32, "b" * 32, "image", "c" * 64)
    assert first.startswith("a" * 32 + "/" + "b" * 32 + "/") and first.endswith(".png")
    assert a.asset_object_key("a" * 32, "d" * 32, "image", "c" * 64) != first
    with pytest.raises(a.InvalidAsset):
        a.asset_object_key("../escape", "b" * 32, "image", "c" * 64)


@pytest.mark.parametrize("suffix", ["docx", "pptx"])
def test_configured_office_images_reach_typed_blocks_without_native_decode(repo_root, monkeypatch, suffix):
    from types import SimpleNamespace

    from common.settings import DeepDocSettings
    from rag.parsers.assets import ParsedAsset
    from rag.parsers.deepdoc_client import DeepDocClient
    from rag.parsers.types import ParseReport, SourceFile

    raw = (repo_root / "test/fixtures/phase6/ocr-planted.png").read_bytes()
    normalized = ParsedAsset.from_png(raw, width=1400, height=400)
    monkeypatch.setattr(DeepDocClient, "normalize_image", lambda self, content: normalized)
    parser = importlib.import_module("rag.parsers." + suffix)
    path = repo_root / f"test/fixtures/phase6/figures-duplicate.{suffix}"
    report = ParseReport()
    settings = SimpleNamespace(deepdoc=DeepDocSettings(url="http://native.test", api_token="a" * 32))
    try:
        blocks = list(parser.parse(SourceFile(path, suffix, path.stat().st_size), report, settings=settings))
    except TypeError as exc:
        if "unexpected keyword argument" in str(exc):
            pytest.fail("configured Office parsing does not yet transport embedded images")
        raise
    images = [asset for block in blocks for asset in block.assets]
    assert len(images) == 2 and len({asset.sha256 for asset in images}) == 1
    assert all(asset.content == raw for asset in images) and report.images_skipped == 0


def test_asset_schema_is_registered_with_document_scoped_digest_uniqueness():
    import api.db.models as models
    from api.db.models.base import index_specs

    model = getattr(models, "DocumentAsset", None)
    assert model is not None, "DocumentAsset ownership relation is missing"
    assert model in models.ALL_MODELS
    assert {"id", "tenant_id", "kb_id", "doc_id", "kind", "object_key", "mime_type", "size", "sha256", "generation_id"} <= set(model._meta.fields)
    assert any(columns == ("tenant_id", "doc_id", "kind", "sha256") and unique for _, columns, unique in index_specs(model))


@pytest.mark.parametrize("suffix", ["docx", "pptx"])
@pytest.mark.parametrize("target,external", [("../../../../escape.png", False), ("https://example.invalid/figure.png", True), ("..%2f..%2f..%2fescape.png", False)])
def test_office_refuses_external_and_escaping_image_relationships(repo_root, tmp_path, monkeypatch, suffix, target, external):
    import zipfile
    from types import SimpleNamespace

    from lxml import etree as ET

    from common.settings import DeepDocSettings
    from rag.parsers.deepdoc_client import DeepDocClient
    from rag.parsers.errors import FileDamaged
    from rag.parsers.types import ParseReport, SourceFile

    original = repo_root / f"test/fixtures/phase6/figures-duplicate.{suffix}"
    path = tmp_path / f"hostile.{suffix}"
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(path, "w") as dest:
        for item in source.infolist():
            raw = source.read(item.filename)
            if item.filename.endswith(".rels"):
                root = ET.fromstring(raw, parser=ET.XMLParser(resolve_entities=False, no_network=True, load_dtd=False))
                for rel in root:
                    if rel.attrib.get("Type", "").endswith("/image"):
                        rel.set("Target", target)
                        if external:
                            rel.set("TargetMode", "External")
                raw = ET.tostring(root)
            dest.writestr(item, raw)

    def no_rpc(*args):
        raise AssertionError("invalid image relationship reached native/storage")

    monkeypatch.setattr(DeepDocClient, "normalize_image", no_rpc)
    settings = SimpleNamespace(deepdoc=DeepDocSettings(url="http://native.test", api_token="a" * 32))
    with pytest.raises(FileDamaged):
        list(importlib.import_module("rag.parsers." + suffix).parse(SourceFile(path, suffix, path.stat().st_size), ParseReport(), settings=settings))
