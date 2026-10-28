"""Whole-document semantics, metadata and pre-provider context safety."""

from types import SimpleNamespace
import pytest
from rag.chunking import factory
from rag.parsers.types import PageBox, ParsedBlock

pytestmark = pytest.mark.unit


def test_one_document_is_one_chunk_with_all_positions_and_owned_images():
    assert factory.available("one"), "One document implementation is missing"
    from rag.parsers.tables import Table, TableCell

    table = Table(1, 1, (TableCell(0, 0, "9100"),), asset_id="c" * 32)
    blocks = [
        ParsedBlock("LIGHTHOUSE 52", boxes=(PageBox(1, 1, 2, 3, 4),), page_sizes={1: (600, 800)}, image_ids=("a" * 32,)),
        ParsedBlock("ORCHARD 9100", boxes=(PageBox(20, 5, 6, 7, 8),), page_sizes={20: (601, 801)}, table=table, image_ids=("c" * 32,)),
        ParsedBlock("", image_ids=("b" * 32, "a" * 32)),
    ]
    (chunk,) = factory.get_chunker("one")(iter(blocks), factory.get_chunker_config("one", {"chunk_token_num": 1}))
    assert chunk.text == "LIGHTHOUSE 52\nORCHARD 9100"
    assert chunk.positions == blocks[0].boxes + blocks[1].boxes
    assert chunk.page_sizes == {1: (600, 800), 20: (601, 801)}
    assert chunk.tables == (table,) and chunk.image_ids == ("a" * 32, "c" * 32, "b" * 32)
    assert chunk.index == 0
    from rag.svr.chunk_doc import build_row

    row = build_row(chunk, index=0, doc_id="d" * 32, kb_id="e" * 32, doc_name="original.pdf", task_id="f" * 32, from_page=0, to_page=20, vector=[1.0], enabled=True)
    assert row["image_ids_kwd"] == list(chunk.image_ids)


def test_empty_one_document_emits_no_chunk_and_oversize_never_splits():
    assert factory.available("one"), "One document implementation is missing"
    from rag.chunking.one import OneConfig, chunk
    from rag.chunking.errors import ChunkTooLong

    assert list(chunk([ParsedBlock(" \n")], OneConfig())) == []
    with pytest.raises(ChunkTooLong):
        list(chunk([ParsedBlock("word " * 20)], OneConfig(max_tokens=3)))


@pytest.mark.parametrize("pages", [[], [[2, 4], [13, 30]], [[1, 8], [4, 30]]])
def test_one_document_schedules_once_even_for_disjoint_or_long_pdf(monkeypatch, pages):
    from api.db.services import ingestion_service

    monkeypatch.setattr(ingestion_service, "pdf_page_count", lambda *a, **kw: 30)
    doc = SimpleNamespace(id="a" * 32, suffix="pdf", location="blob", content_hash="hash", parser_id="one", parser_config={"pages": pages})
    settings = SimpleNamespace(ingest=SimpleNamespace(task_page_size=12))
    assert ingestion_service._page_ranges(settings, object(), doc) == [(0, 30)]


def test_one_selected_page_ranges_merge_without_including_gaps():
    assert factory.available("one"), "One document implementation is missing"
    from rag.parsers.page_selection import selected_ranges

    assert selected_ranges([[2, 4], [3, 5], [13, 30]], (0, 30)) == [(1, 5), (12, 30)]


def test_actual_embedding_context_refuses_before_provider_truncation(monkeypatch):
    from rag.svr.embedding import EmbedRunner
    from rag.svr.failure import TaskFailure
    from contextlib import nullcontext

    called = []
    bundle = SimpleNamespace(token_limit=3, encode=lambda texts: (called.append(texts) or [[1.0]], 0))
    runner = EmbedRunner(SimpleNamespace(), SimpleNamespace(embed_limiter=nullcontext()))
    monkeypatch.setattr(runner, "_bundle", lambda *a: bundle)
    monkeypatch.setattr("rag.svr.embedding.release_database_connection", lambda: None)
    with pytest.raises(TaskFailure) as error:
        runner._encode_blocking(["word " * 10], SimpleNamespace(parser_id="one"), 1)
    assert error.value.code == "chunk_too_long" and error.value.terminal
    assert called == []


def test_catalog_public_exceptions_are_exact_gets_and_all_other_paths_deny():
    from api.apps.route_policy_gen import policy_for

    for path in ["/api/v1/pipelines", "/api/v1/pipelines/one"]:
        public = policy_for("GET", path)
        assert (public.owner, public.auth, public.scope) == ("go", "none", "none")
        assert policy_for("POST", path).auth == "jwt"
    assert policy_for("GET", "/api/v1/pipelines/one/private").auth == "jwt"


def test_static_catalog_matches_python_implementation_availability(repo_root):
    import json

    templates = json.loads((repo_root / "internal/pipeline/templates.json").read_text())
    assert [t["id"] for t in templates] == list(factory.METHODS)
    assert {t["id"] for t in templates if t["available"]} == {"naive", "one", "manual", "qa", "book"}
    assert all(t["available"] == factory.available(t["parser_id"]) for t in templates)
    assert all(set(t) == {"id", "name", "description", "parser_id", "parser_config", "available"} for t in templates)


@pytest.mark.parametrize("method,path", [("POST", "/api/v1/pipelines"), ("GET", "/api/v1/pipelines/{id}/private")])
def test_public_registry_allowance_cannot_expand_to_other_methods_or_subpaths(repo_root, tmp_path, method, path):
    import yaml
    from scripts.gen_routes import load, load_endpoints, RouteError

    data = yaml.safe_load((repo_root / "conf/routes.yaml").read_text())
    data["endpoints"].append({"method": method, "path": path, "owner": "go", "auth": "none", "roles": [], "scope": "none", "implemented": True})
    changed = tmp_path / "routes.yaml"
    changed.write_text(yaml.safe_dump(data))
    _, routes = load(changed)
    with pytest.raises(RouteError, match="disagrees with family"):
        load_endpoints(changed, routes)


def test_catalog_schema_describes_go_without_registering_python_controller():
    from api.apps import create_app
    from api.apps.catalog_schema import CatalogOpenAPIProvider
    from test.helpers.app import memory_settings

    app = create_app(memory_settings())
    assert not any("/pipelines" in rule.rule for rule in app.url_map.iter_rules())
    provider = app.extensions["QUART_SCHEMA"].openapi_provider
    assert isinstance(provider, CatalogOpenAPIProvider)
    paths = provider.schema()["paths"]
    for path in ["/api/v1/pipelines", "/api/v1/pipelines/{id}"]:
        assert paths[path]["get"]["x-api-owner"] == "go"
        assert paths[path]["get"]["security"] == []
