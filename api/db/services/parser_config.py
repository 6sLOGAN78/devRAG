"""Typed parser configuration (plan 04-15; BE-09, D-31).

``ParserConfig`` types and bounds the keys the chunker reads. Unknown keys are kept. A delimiter is a set of characters and is never
compiled as a pattern. Messages never hold the submitted value. This module imports no web framework.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, ValidationError, field_validator

from api.db.services.service_errors import Kind, ServiceError
from api.utils import reasons
from common.ingest_codes import IMPLEMENTED_PARSERS

MAX_PARSER_CONFIG = 4096
MAX_DELIMITER = 64


class ParserConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    chunk_token_num: StrictInt = Field(default=512, ge=1, le=8192)
    delimiter: StrictStr = Field(default="\n", min_length=1, max_length=MAX_DELIMITER)
    overlapped_percent: StrictInt = Field(default=0, ge=0, le=50)
    pages: list[tuple[StrictInt, StrictInt]] = Field(default_factory=list, max_length=128)
    layout_recognize: StrictBool | StrictStr = True
    auto_keywords: StrictInt = Field(default=0, ge=0, le=32)
    table_context_size: StrictInt = Field(default=0, ge=0)
    asr_model: StrictStr = Field(default="", max_length=128)
    audio_language: StrictStr | None = Field(default=None, pattern=r"^[a-z]{2,3}$")
    image_model: StrictStr = Field(default="",max_length=128)
    picture_ocr_only: StrictBool = False
    image_context_size: StrictInt = Field(default=0, ge=0)

    @field_validator("pages")
    @classmethod
    def _ordered(cls, value: list[tuple[int, int]]) -> list[tuple[int, int]]:
        if any(start < 1 or start > end for start, end in value):
            raise ValueError("page ranges must satisfy 0 < start <= end")
        return value


def _default_structural(message: str) -> ServiceError:
    return ServiceError(Kind.INVALID, reasons.PARSER_CONFIG_INVALID, message)


def _field_error(field: str | None) -> ServiceError:
    return ServiceError(Kind.INVALID, reasons.PARSER_CONFIG_INVALID, "a parser setting is not valid", data={"field": field} if field else None)


def validate_parser_config(raw: object, *, structural: Callable[[str], ServiceError] = _default_structural) -> dict[str, Any]:
    """The validated configuration as a plain dict (unknown keys kept; only keys that were sent are returned).

    Shape problems (not an object, not JSON, over the size cap) are raised through ``structural`` so a caller keeps its own reason.
    A bad known value, or nesting too deep to process, is ``parser_config_invalid`` with ``data.field``.
    """
    if not isinstance(raw, dict):
        raise structural("the parser configuration must be an object")
    try:
        encoded = json.dumps(raw, ensure_ascii=False)
    except RecursionError:
        raise _field_error(None) from None
    except (TypeError, ValueError):
        raise structural("the parser configuration is not valid") from None
    if len(encoded) > MAX_PARSER_CONFIG:
        raise structural(f"the parser configuration is over {MAX_PARSER_CONFIG} characters")
    try:
        model = ParserConfig.model_validate(raw)
        out = model.model_dump(exclude_unset=True)
    except ValidationError as exc:
        errors = exc.errors()
        loc = errors[0]["loc"] if errors else ()
        raise _field_error(str(loc[0]) if loc else None) from None
    except RecursionError:
        raise _field_error(None) from None
    if "pages" in out:
        out["pages"] = [[start, end] for start, end in out["pages"]]
    return out


def require_buildable(parser_id: object) -> None:
    """A chunking method must have a built chunker before it can be set on an existing dataset or document."""
    if not isinstance(parser_id, str) or parser_id not in IMPLEMENTED_PARSERS:
        raise ServiceError(Kind.INVALID, reasons.CHUNKER_UNAVAILABLE, "that chunking method is not available yet")
