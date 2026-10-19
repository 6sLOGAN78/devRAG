"""Pure assistant validation rules (plan 05-07; CHAT-05..07). No database."""

from __future__ import annotations

import pytest

from api.db.models.chat import Dialog
from api.db.services import dialog_rules as rules
from api.db.services.service_errors import Kind, ServiceError

pytestmark = pytest.mark.unit


def _refused(call) -> ServiceError:
    with pytest.raises(ServiceError) as err:
        call()
    return err.value


def test_defaults_equal_the_model_column_defaults() -> None:
    assert rules.DEFAULT_LLM_SETTING == Dialog.llm_setting.default()
    assert rules.DEFAULT_PROMPT_CONFIG == Dialog.prompt_config.default()
    assert rules.DEFAULT_SIMILARITY_THRESHOLD == Dialog.similarity_threshold.default
    assert rules.DEFAULT_VECTOR_SIMILARITY_WEIGHT == Dialog.vector_similarity_weight.default
    assert rules.DEFAULT_TOP_N == Dialog.top_n.default


def test_llm_setting_merges_over_the_base_and_keeps_the_rest() -> None:
    assert rules.sanitize_llm_setting({"temperature": 1.0})["max_tokens"] == 512
    assert rules.sanitize_llm_setting({"max_tokens": 9}, {"temperature": 0.5, "max_tokens": 1})["temperature"] == 0.5
    assert rules.sanitize_llm_setting(None) == rules.DEFAULT_LLM_SETTING


@pytest.mark.parametrize(
    "bad",
    [{"temperature": -0.01}, {"temperature": 2.01}, {"top_p": 1.01}, {"frequency_penalty": -2.01}, {"presence_penalty": 2.01}, {"max_tokens": 0}, {"max_tokens": 8193},
     {"max_tokens": 1.5}, {"temperature": True}, {"temperature": "0.5"}, {"temperature": float("inf")}, {"stop": []}, {"model": "x"}],
)  # fmt: skip
def test_llm_setting_out_of_range_is_fields_invalid(bad) -> None:
    err = _refused(lambda: rules.sanitize_llm_setting(bad))
    assert (err.kind, err.reason) == (Kind.INVALID, "fields_invalid")


def test_llm_setting_must_be_an_object() -> None:
    assert _refused(lambda: rules.sanitize_llm_setting([1])).reason == "fields_invalid"


def test_prompt_config_accepts_three_keys_and_keeps_parameters() -> None:
    merged = rules.merge_prompt_config({"system": "be brief"}, rules.DEFAULT_PROMPT_CONFIG)
    assert merged["system"] == "be brief" and merged["parameters"] == [] and merged["empty_response"]
    assert _refused(lambda: rules.merge_prompt_config({"parameters": [{"key": "x"}]}, {})).reason == "fields_invalid"
    assert _refused(lambda: rules.merge_prompt_config({"empty_response": " "}, {})).reason == "fields_invalid"


def test_update_with_no_fields_is_refused_but_create_reports_the_missing_name_first() -> None:
    assert _refused(lambda: rules.validate_fields({}, creating=False)).reason == "fields_invalid"
    assert _refused(lambda: rules.validate_fields({}, creating=True)).reason == "fields_invalid"
    assert _refused(lambda: rules.validate_fields({"name": "x"}, creating=True)).reason == "model_unavailable"


def test_validate_fields_returns_only_the_keys_sent_and_trims_the_name() -> None:
    assert rules.validate_fields({"name": "  Bot  "}, creating=False) == {"name": "Bot"}
    assert rules.validate_fields({"rerank_id": None, "icon": None}, creating=False) == {"rerank_id": "", "icon": ""}
    assert rules.validate_fields({"top_n": 3}, creating=False) == {"top_n": 3}


def test_validate_fields_dedupes_dataset_ids_and_treats_a_malformed_id_as_a_miss() -> None:
    one = "a" * 32
    assert rules.validate_fields({"kb_ids": [one, one]}, creating=False) == {"kb_ids": [one]}
    err = _refused(lambda: rules.validate_fields({"kb_ids": ["short"]}, creating=False))
    assert (err.kind, err.reason) == (Kind.NOT_FOUND, "dataset_not_found")


@pytest.mark.parametrize("icon", ["data:image/png;base64,AA==", "data:image/jpeg;base64,/9j/4AAQ", ""])
def test_icon_accepts_png_and_jpeg_data_urls(icon: str) -> None:
    assert rules.validate_fields({"icon": icon}, creating=False) == {"icon": icon}


@pytest.mark.parametrize("icon", ["data:image/gif;base64,AA==", "data:image/png;base64,<b>", "data:image/png,AA==", "http://x/a.png", "data:image/png;base64,AA==" + "A" * rules.MAX_ICON])
def test_icon_refuses_other_content(icon: str) -> None:
    assert _refused(lambda: rules.validate_fields({"icon": icon}, creating=False)).reason == "fields_invalid"


def test_is_id_is_32_lowercase_hex() -> None:
    assert rules.is_id("0" * 32) and not rules.is_id("0" * 31) and not rules.is_id("G" * 32) and not rules.is_id(None)
