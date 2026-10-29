"""ParserConfig validation (plan 04-15, BE-09, D-31)."""

from __future__ import annotations

import pytest

from api.db.services.parser_config import require_buildable, validate_parser_config
from api.db.services.service_errors import Kind, ServiceError


def refused(raw: object) -> ServiceError:
    with pytest.raises(ServiceError) as err:
        validate_parser_config(raw)
    return err.value


@pytest.mark.parametrize(
    ("raw", "field"),
    [
        ({"chunk_token_num": -5}, "chunk_token_num"),
        ({"chunk_token_num": 0}, "chunk_token_num"),
        ({"chunk_token_num": 9000}, "chunk_token_num"),
        ({"chunk_token_num": "x"}, "chunk_token_num"),
        ({"chunk_token_num": True}, "chunk_token_num"),
        ({"delimiter": 7}, "delimiter"),
        ({"delimiter": ""}, "delimiter"),
        ({"delimiter": "d" * 65}, "delimiter"),
        ({"overlapped_percent": 51}, "overlapped_percent"),
        ({"overlapped_percent": -1}, "overlapped_percent"),
        ({"pages": "x"}, "pages"),
        ({"pages": [[1]]}, "pages"),
        ({"pages": [[5, 2]]}, "pages"),
        ({"pages": [[0, 2]]}, "pages"),
        ({"auto_keywords": 33}, "auto_keywords"),
        ({"table_context_size": -1}, "table_context_size"),
        ({"image_context_size": -1}, "image_context_size"),
    ],
)
def test_a_bad_known_value_is_typed_and_names_the_field(raw, field):
    err = refused(raw)
    assert err.kind is Kind.INVALID and err.reason == "parser_config_invalid"
    assert err.data == {"field": field}


def test_a_valid_config_keeps_unknown_keys():
    out = validate_parser_config({"chunk_token_num": 512, "delimiter": "\\n", "overlapped_percent": 10, "unknown_key": {"a": 1}})
    assert out == {"chunk_token_num": 512, "delimiter": "\\n", "overlapped_percent": 10, "unknown_key": {"a": 1}}


def test_the_documented_defaults_validate():
    out = validate_parser_config({"pages": [[1, 1000000]], "layout_recognize": True, "auto_keywords": 0, "table_context_size": 0, "image_context_size": 0})
    assert out["pages"] == [[1, 1000000]] or out["pages"] == [(1, 1000000)]


def test_deep_nesting_is_a_typed_error_not_a_recursion_error():
    deep: dict = {}
    node = deep
    for _ in range(1200):
        node["n"] = {}
        node = node["n"]
    err = refused(deep)
    assert err.kind is Kind.INVALID and err.reason == "parser_config_invalid"


def test_the_size_cap_and_shape_checks_keep_a_refusal():
    assert refused({"k": "v" * 4100}).reason == "parser_config_invalid"
    assert refused([1]).reason == "parser_config_invalid"
    assert refused({"k": {1, 2}}).reason == "parser_config_invalid"


def test_a_structural_refusal_can_use_the_callers_error():
    def mine(message: str) -> ServiceError:
        return ServiceError(Kind.INVALID, "parser_invalid", message)

    with pytest.raises(ServiceError) as err:
        validate_parser_config([1], structural=mine)
    assert err.value.reason == "parser_invalid"


def test_messages_do_not_echo_the_value():
    err = refused({"delimiter": "secret-" * 20})
    assert "secret" not in err.message


def test_require_buildable():
    for parser_id in ("naive", "qa", "paper", "email", "resume"):
        require_buildable(parser_id)
    for parser_id in ("tag", "bogus"):
        with pytest.raises(ServiceError) as err:
            require_buildable(parser_id)
        assert err.value.kind is Kind.INVALID and err.value.reason == "chunker_unavailable"
