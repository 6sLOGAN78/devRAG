"""Document metadata contract, frozen before the producer implementation."""
import json

import pytest

from api.db.models.knowledge import Document

pytestmark = pytest.mark.unit


def test_document_has_persistent_bounded_metadata_column(repo_root):
    annotation = json.loads((repo_root / "test/fixtures/phase6/metadata-original-annotation.json").read_text())
    source = (repo_root / "test/fixtures/phase6/tags-original.txt").read_text()
    assert "52 metres" in source and "73 units" in source
    assert annotation["facts"]["height_metres"] == 52
    assert "meta_fields" in Document._meta.fields, "Document metadata has no persistent column"
    field = Document._meta.fields["meta_fields"]
    assert field.null is False


def test_metadata_merge_preserves_unmentioned_fields_and_null_is_stored():
    from api.db.services.document_metadata_service import merge_metadata, validate_metadata

    old = {"subject": "lighthouse", "height_metres": 52}
    incoming = validate_metadata({"offset_units": 73, "reviewed": None})
    assert merge_metadata(old, incoming, mode="merge") == {
        "subject": "lighthouse", "height_metres": 52, "offset_units": 73, "reviewed": None,
    }
    assert merge_metadata(old, incoming, mode="replace") == incoming


def test_metadata_rejects_reserved_colliding_and_unbounded_fields():
    from api.db.services.document_metadata_service import validate_metadata

    invalid = [
        {"_provenance": "forged"}, {"a.b": 1}, {"a/b": 1},
        {"A": 1, "a": 2}, {"nested": {"bad": True}},
        {"nonfinite": float("nan")}, {"many": list(range(101))},
        {"x" * 65: "v"}, {f"field_{i}": i for i in range(33)},
        {"large": "x" * 17000},
    ]
    for value in invalid:
        with pytest.raises(ValueError):
            validate_metadata(value)


def test_metadata_flattening_has_stable_typed_values_and_bounds():
    from api.db.services.document_metadata_service import flatten_metadata

    rows = [
        {"subject": "lighthouse", "height_metres": 52, "reviewed": True},
        {"subject": "lighthouse", "height_metres": 73, "reviewed": False},
    ]
    assert flatten_metadata(rows) == [
        {"name": "height_metres", "type": "number", "total": 2, "values": [52, 73]},
        {"name": "reviewed", "type": "boolean", "total": 2, "values": [False, True]},
        {"name": "subject", "type": "string", "total": 1, "values": ["lighthouse"]},
    ]
    pages = [{"ordinal": number} for number in range(101)]
    first = flatten_metadata(pages)
    second = flatten_metadata(pages, page=2)
    assert first[0]["total"] == 101 and len(first[0]["values"]) == 100
    assert second[0]["total"] == 101 and second[0]["values"] == [100]
    assert flatten_metadata([{"kind": 52}, {"kind": "lighthouse"}])[0]["type"] == "mixed"


def test_worker_row_contains_bounded_metadata_without_source_or_geometry_rewrite():
    from rag.chunking.types import Chunk
    from rag.svr.chunk_doc import build_row
    from rag.svr.failure import TaskFailure

    chunk = Chunk(text="Lighthouse height: 52 metres.", positions=(), page_sizes={}, token_num=7, index=0)
    args = dict(index=0, doc_id="d" * 32, kb_id="a" * 32, doc_name="original.txt", task_id="t" * 32, from_page=0, to_page=1, vector=[1.0], enabled=True)
    before = build_row(chunk, **args)
    after = build_row(chunk, **args, meta_fields={"height_metres": 52})
    assert json.loads(after["meta_fields_list"]) == {"height_metres": 52}
    assert after["content_with_weight"] == before["content_with_weight"]
    assert after["position_int"] == before["position_int"]
    assert after["q_1_vec"] == before["q_1_vec"]
    with pytest.raises(TaskFailure):
        build_row(chunk, **args, meta_fields={"oversize": "x" * 17000})


def test_metadata_configuration_schema_is_typed_and_bounded():
    from api.db.services.parser_config import validate_parser_config
    result = validate_parser_config({"auto_metadata": True, "metadata_schema": [{"name": "Height_Metres", "type": "number", "required": True}], "metadata_model_id": "local-chat"})
    assert result["metadata_schema"] == [{"name": "height_metres", "type": "number", "required": True}]
    for schema in ([{"name": "a.b", "type": "string"}], [{"name": "a", "type": "code"}], [{"name": "A", "type": "string"}, {"name": "a", "type": "string"}], [{"name": "_provenance", "type": "string"}]):
        with pytest.raises(Exception):
            validate_parser_config({"metadata_schema": schema})


@pytest.mark.parametrize("method,path", [
    ("PATCH", "/api/v1/datasets/<dataset_id>/documents/metadatas"),
    ("GET", "/api/v1/datasets/metadata/flattened"),
    ("GET", "/api/v1/datasets/<dataset_id>/metadata/config"),
])
def test_metadata_routes_have_private_handlers(method, path):
    from api.apps import create_app

    app = create_app()
    assert any(rule.rule == path and method in rule.methods for rule in app.url_map.iter_rules())
