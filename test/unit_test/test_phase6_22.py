"""Original controlled tagging and generated metadata contract."""
import pytest
import json
from pydantic import ValidationError
from api.db.services.parser_config import ParserConfig
from rag.svr.enrichment import parse_controlled_tags, parse_generated_metadata
from rag.svr.failure import TaskFailure
from api.db.services.document_metadata_service import _merged_stored, effective_metadata, metadata_provenance

pytestmark = pytest.mark.unit


def test_controlled_tag_set_is_typed_bounded_and_off_by_default():
    assert ParserConfig().auto_tags is False
    assert ParserConfig().allowed_tags == []
    enabled = ParserConfig.model_validate({"auto_tags": True, "allowed_tags": ["lighthouse", "calibration"], "tag_model_id": "model@provider"})
    assert enabled.allowed_tags == ["calibration", "lighthouse"]
    with pytest.raises(ValidationError):
        ParserConfig.model_validate({"auto_tags": True, "allowed_tags": ["lighthouse", "lighthouse"]})


def test_controlled_tags_accept_only_declared_labels_and_exact_chunk_order():
    raw = json.dumps({"items": [{"index": 0, "tags": ["lighthouse", "calibration"]}, {"index": 1, "tags": []}]})
    assert parse_controlled_tags(raw, 2, ["calibration", "lighthouse"]) == (("calibration", "lighthouse"), ())
    for bad in (
        {"items": [{"index": 0, "tags": ["private-owner"]}]},
        {"items": [{"index": 1, "tags": ["lighthouse"]}]},
        {"items": [{"index": 0, "tags": [17]}]},
    ):
        with pytest.raises(TaskFailure):
            parse_controlled_tags(json.dumps(bad), 1, ["calibration", "lighthouse"])
    with pytest.raises(TaskFailure):
        parse_controlled_tags('{"items":[{"index":0,"tags":["lighthouse"],"tags":["private-owner"]}]}', 1, ["lighthouse"])


def test_generated_metadata_requires_exact_schema_types_and_bounded_values():
    schema = [{"name": "tower_height_metres", "type": "number", "required": True}, {"name": "reviewed", "type": "boolean", "required": False}]
    assert parse_generated_metadata('{"metadata":{"tower_height_metres":52,"reviewed":false}}', schema) == {"reviewed": False, "tower_height_metres": 52}
    for bad in (
        {"metadata": {"tower_height_metres": True}},
        {"metadata": {"tower_height_metres": 52, "private_owner": "Ada"}},
        {"metadata": {"reviewed": False}},
        {"metadata": {"tower_height_metres": "52"}},
    ):
        with pytest.raises(TaskFailure):
            parse_generated_metadata(json.dumps(bad), schema)
    with pytest.raises(TaskFailure):
        parse_generated_metadata('{"metadata":{"tower_height_metres":52,"tower_height_metres":73}}', schema)


def test_human_edit_wins_without_erasing_generated_origin_or_exceeding_public_bound():
    stored = {"_generated": {"tower_height_metres": 52}, "_provenance": {"tower_height_metres": "generated:0000000000:task"}}
    edited = _merged_stored(stored, {"tower_height_metres": 53}, "merge")
    assert edited["_generated"] == {"tower_height_metres": 52}
    assert effective_metadata(edited) == {"tower_height_metres": 53}
    assert metadata_provenance(edited) == {"tower_height_metres": "human"}
    full = {f"field{i}": i for i in range(32)}
    with pytest.raises(ValueError):
        _merged_stored({"_generated": full}, {"extra": 1}, "merge")
