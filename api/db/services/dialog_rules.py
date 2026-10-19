"""Pure validation for chat assistants (plan 05-07; CHAT-01..07, D-08, D-10).

Nothing here touches the database or a model service. :func:`validate_fields` turns a create or update body into the values that may be
stored, raising ``ServiceError`` with a stable reason for the first thing that is wrong. A key that is absent from an update body is not a
change; ``null`` clears only the optional fields (``icon``, ``rerank_id``). Messages never repeat the caller's input.

Stored settings and their bounds:

* ``prompt_config``: ``system`` (at most 8000 characters), ``prologue`` (at most 500), ``empty_response`` (1 to 500, not blank). Other
  prompt variables are an advanced feature and are not accepted (CHAT-05 Partial).
* ``llm_setting``: ``temperature`` 0..2, ``top_p`` 0..1, ``frequency_penalty`` and ``presence_penalty`` -2..2, ``max_tokens`` 1..8192 (CHAT-06).
* ``similarity_threshold`` and ``vector_similarity_weight`` in [0, 1], ``top_n`` 1..30 (CHAT-07).
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any

from api.db.services.service_errors import Kind, ServiceError
from api.db.services.tenant_scope import PERMISSION_ME, PERMISSION_TEAM
from api.utils import reasons

PERMISSIONS = (PERMISSION_ME, PERMISSION_TEAM)
MAX_NAME = 128
MAX_ICON = 400_000
ICON_PREFIXES = ("data:image/png;base64,", "data:image/jpeg;base64,")
MAX_KB_IDS = 20
MAX_STORED_KB_IDS = 100  # the visible ids a saver chooses plus the ids kept for other readers (D-25); bounds the row
MAX_SYSTEM = 8000
MAX_PROLOGUE = 500
MAX_EMPTY_RESPONSE = 500
MAX_TOP_N = 30
MAX_MAX_TOKENS = 8192
MAX_PAGE_SIZE = 100
CREATE_FIELDS = frozenset(
    {"name", "icon", "permission", "kb_ids", "llm_id", "rerank_id", "similarity_threshold", "vector_similarity_weight", "top_n", "prompt_config", "llm_setting"}
)
NEVER_NULL_FIELDS = ("name", "permission", "kb_ids", "similarity_threshold", "vector_similarity_weight", "top_n", "prompt_config", "llm_setting")
DEFAULT_PROMPT_CONFIG: dict[str, Any] = {
    "system": "",
    "prologue": "Hi! I'm your assistant. What can I do for you?",
    "parameters": [],
    "empty_response": "Sorry! No relevant content was found in the knowledge base!",
}
DEFAULT_LLM_SETTING: dict[str, Any] = {"temperature": 0.1, "top_p": 0.3, "frequency_penalty": 0.7, "presence_penalty": 0.4, "max_tokens": 512}
DEFAULT_SIMILARITY_THRESHOLD = 0.2
DEFAULT_VECTOR_SIMILARITY_WEIGHT = 0.3
DEFAULT_TOP_N = 6
_PROMPT_KEYS = ("system", "prologue", "empty_response")
_LLM_BOUNDS: dict[str, tuple[float, float, bool]] = {
    "temperature": (0, 2, False),
    "top_p": (0, 1, False),
    "frequency_penalty": (-2, 2, False),
    "presence_penalty": (-2, 2, False),
    "max_tokens": (1, MAX_MAX_TOKENS, True),
}
_ID = re.compile(r"[0-9a-f]{32}")
_BASE64 = re.compile(r"[A-Za-z0-9+/]*={0,2}")


def invalid(message: str) -> ServiceError:
    return ServiceError(Kind.INVALID, reasons.FIELDS_INVALID, message)


def is_id(value: object) -> bool:
    """True for a well-formed assistant or dataset id (32 lowercase hex characters)."""
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def _number(value: object, low: float, high: float, label: str, *, integer: bool = False) -> int | float:
    """A finite number within ``[low, high]``. A boolean is not a number here."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise invalid(f"{label} is not valid")
    if isinstance(value, float) and not math.isfinite(value):
        raise invalid(f"{label} is not valid")
    if integer and not isinstance(value, int):
        raise invalid(f"{label} is not valid")
    if not low <= value <= high:
        raise invalid(f"{label} is out of range")
    return value if integer else float(value)


def sanitize_llm_setting(value: object, base: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The generation settings after applying ``value`` over ``base`` (the defaults when absent); every key is bounded (CHAT-06).

    Raises ``ServiceError`` (``fields_invalid``) for an unknown key, a non-number or a number out of range, so a stored value is always safe
    to hand to the model driver.
    """
    merged: dict[str, Any] = dict(DEFAULT_LLM_SETTING if base is None else base)
    if value is None:
        return merged
    if not isinstance(value, Mapping):
        raise invalid("the model settings must be an object")
    if not set(value) <= set(_LLM_BOUNDS):
        raise invalid("some of those model settings are not supported")
    for key, sent in value.items():
        low, high, integer = _LLM_BOUNDS[key]
        merged[key] = _number(sent, low, high, f"the {key.replace('_', ' ')}", integer=integer)
    return merged


def _prompt_text(value: object, limit: int, label: str, *, required: bool = False) -> str:
    if not isinstance(value, str) or len(value) > limit:
        raise invalid(f"{label} is not valid")
    if required and not value.strip():
        raise invalid(f"{label} is required")
    return value


def merge_prompt_config(value: object, base: Mapping[str, Any]) -> dict[str, Any]:
    """``value`` applied over ``base``; only ``system``, ``prologue`` and ``empty_response`` can be sent."""
    merged: dict[str, Any] = {**DEFAULT_PROMPT_CONFIG, **dict(base)}
    if not isinstance(value, Mapping):
        raise invalid("the prompt settings must be an object")
    if not set(value) <= set(_PROMPT_KEYS):
        raise invalid("some of those prompt settings are not supported")
    if "system" in value:
        merged["system"] = _prompt_text(value["system"], MAX_SYSTEM, "the system prompt")
    if "prologue" in value:
        merged["prologue"] = _prompt_text(value["prologue"], MAX_PROLOGUE, "the greeting")
    if "empty_response" in value:
        merged["empty_response"] = _prompt_text(value["empty_response"], MAX_EMPTY_RESPONSE, "the no-answer reply", required=True)
    return merged


def _icon(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > MAX_ICON:
        raise invalid("the icon is not valid")
    if not value:
        return ""
    prefix = next((p for p in ICON_PREFIXES if value.startswith(p)), None)
    if prefix is None or _BASE64.fullmatch(value, len(prefix)) is None:
        raise invalid("the icon must be a PNG or JPEG image")
    return value


def _kb_ids(value: object) -> list[str]:
    """Distinct dataset ids in request order. A malformed id is the same miss as an absent dataset (``dataset_not_found``)."""
    if not isinstance(value, (list, tuple)) or len(value) > MAX_KB_IDS:
        raise invalid(f"choose at most {MAX_KB_IDS} datasets")
    clean: list[str] = []
    for item in value:
        if not is_id(item):
            raise ServiceError(Kind.NOT_FOUND, reasons.DATASET_NOT_FOUND, "not found")
        if item not in clean:
            clean.append(item)
    if len(clean) > MAX_KB_IDS:
        raise invalid(f"choose at most {MAX_KB_IDS} datasets")
    return clean


def validate_fields(body: object, *, creating: bool) -> dict[str, Any]:
    """The values a body may store, keyed by field. ``prompt_config`` and ``llm_setting`` come back as the partial objects that were sent.

    Creating requires ``name`` and ``llm_id``. Model ids are returned as sent; the caller resolves them against the workspace.
    """
    if not isinstance(body, Mapping):
        raise invalid("the request is not valid")
    if not body and not creating:
        raise invalid("send at least one field to change")
    if not set(body) <= CREATE_FIELDS:
        raise invalid("some of those fields cannot be set")
    if any(key in body and body[key] is None for key in NEVER_NULL_FIELDS):
        raise invalid("a field that cannot be cleared was sent empty")
    if creating and "name" not in body:
        raise invalid("the name is required")
    if creating and "llm_id" not in body:
        raise ServiceError(Kind.INVALID, reasons.MODEL_UNAVAILABLE, "choose a chat model")
    out: dict[str, Any] = {}
    if "name" in body:
        name = body["name"]
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= MAX_NAME:
            raise invalid(f"the name must be 1 to {MAX_NAME} characters")
        out["name"] = name.strip()
    if "icon" in body:
        out["icon"] = _icon(body["icon"])
    if "permission" in body:
        if body["permission"] not in PERMISSIONS:
            raise invalid("permission must be me or team")
        out["permission"] = body["permission"]
    if "kb_ids" in body:
        out["kb_ids"] = _kb_ids(body["kb_ids"])
    for key in ("llm_id", "rerank_id"):
        if key in body:
            sent = body[key]
            if sent is not None and not isinstance(sent, str):
                raise ServiceError(Kind.INVALID, reasons.MODEL_UNAVAILABLE, "that model is not available in this workspace")
            out[key] = sent or ""
    if "similarity_threshold" in body:
        out["similarity_threshold"] = _number(body["similarity_threshold"], 0, 1, "the similarity threshold")
    if "vector_similarity_weight" in body:
        out["vector_similarity_weight"] = _number(body["vector_similarity_weight"], 0, 1, "the vector similarity weight")
    if "top_n" in body:
        out["top_n"] = _number(body["top_n"], 1, MAX_TOP_N, "the number of passages", integer=True)
    if "prompt_config" in body:
        merge_prompt_config(body["prompt_config"], {})  # shape and bounds of what was sent; the merge over stored values happens at write
        out["prompt_config"] = dict(body["prompt_config"])
    if "llm_setting" in body:
        sanitize_llm_setting(body["llm_setting"])
        out["llm_setting"] = dict(body["llm_setting"])
    return out
