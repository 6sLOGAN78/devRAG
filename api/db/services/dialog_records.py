"""Frozen assistant records and the response body built from them (plan 05-07).

The view lists its keys explicitly, so a column added to the table never reaches a client unreviewed. It says ``id``, never ``dialog_id``, and
``permission``, never ``status`` or ``source`` (the response leak sweep bans those names).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from api.db.models import Dialog
from api.db.services.dialog_rules import DEFAULT_LLM_SETTING, DEFAULT_PROMPT_CONFIG
from api.db.services.tenant_scope import ActingScope


@dataclass(frozen=True)
class AssistantRecord:
    id: str
    tenant_id: str
    name: str
    icon: str
    permission: str
    created_by: str
    kb_ids: tuple[str, ...]
    llm_id: str
    rerank_id: str
    similarity_threshold: float
    vector_similarity_weight: float
    top_n: int
    prompt_config: dict[str, Any]
    llm_setting: dict[str, Any]
    create_time: int
    update_time: int


@dataclass(frozen=True)
class VisibleAssistant:
    assistant: AssistantRecord
    scope: ActingScope


@dataclass(frozen=True)
class ChatBinding:
    """What a turn may retrieve from, decided for one reader (D-25)."""

    assistant: AssistantRecord
    usable_dataset_ids: tuple[str, ...]
    unavailable_count: int
    tenant_id: str


def record_of(row: Dialog, *, with_icon: bool = True) -> AssistantRecord:
    stored_ids = row.kb_ids if isinstance(row.kb_ids, list) else []
    prompt = row.prompt_config if isinstance(row.prompt_config, dict) else {}
    setting = row.llm_setting if isinstance(row.llm_setting, dict) else {}
    return AssistantRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name or "",
        icon=(row.icon or "") if with_icon else "",
        permission=row.permission,
        created_by=row.created_by,
        kb_ids=tuple(i for i in stored_ids if isinstance(i, str)),
        llm_id=row.llm_id,
        rerank_id=row.rerank_id or "",
        similarity_threshold=float(row.similarity_threshold),
        vector_similarity_weight=float(row.vector_similarity_weight),
        top_n=int(row.top_n),
        prompt_config={**DEFAULT_PROMPT_CONFIG, **prompt},
        llm_setting={**DEFAULT_LLM_SETTING, **setting},
        create_time=int(row.create_time or 0),
        update_time=int(row.update_time or 0),
    )


def assistant_view(
    record: AssistantRecord, *, usable_ids: Sequence[str], include_icon: bool, members_with_chats: int | None = None
) -> dict[str, Any]:
    """The response body. Keys are listed here, so a column added to the table never reaches a client unreviewed.

    ``kb_ids`` holds only the ids the reader can open; ``unavailable_datasets`` is how many bound ids this reader does not get.
    """
    prompt = record.prompt_config
    out: dict[str, Any] = {"id": record.id, "name": record.name}
    if include_icon:
        out["icon"] = record.icon
    out.update(
        {
            "permission": record.permission,
            "created_by": record.created_by,
            "kb_ids": list(usable_ids),
            "unavailable_datasets": len(record.kb_ids) - len(usable_ids),
        }
    )
    if members_with_chats is not None:
        out["members_with_chats"] = members_with_chats
    out.update(
        {
            "llm_id": record.llm_id,
            "rerank_id": record.rerank_id,
            "similarity_threshold": record.similarity_threshold,
            "vector_similarity_weight": record.vector_similarity_weight,
            "top_n": record.top_n,
            "prompt_config": {"system": prompt["system"], "prologue": prompt["prologue"], "empty_response": prompt["empty_response"]},
            "llm_setting": dict(record.llm_setting),
            "update_time": record.update_time,
        }
    )
    return out
