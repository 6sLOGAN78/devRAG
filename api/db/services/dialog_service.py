"""Chat assistants: create, list, read, update, delete and the per-reader dataset set for a turn (plan 05-07; CHAT-01..07, D-08..D-11, D-23..D-26).

An assistant is a ``dialog`` row of one workspace. Any member can create one; it is private to its creator (``permission = "me"``) until it is
shared with the team (``"team"``), mirroring a dataset (D-08, D-09). A private assistant is invisible to everyone else, owners and admins
included, and every miss is the one ``NOT_FOUND`` (D-19). The rules, as built:

* Binding (D-10). A ``team`` assistant binds only ``team`` datasets; a private one binds any dataset its creator can open. Widening to ``team``
  checks every bound dataset that still exists (those the saver cannot open included); a ``team`` assistant that stays ``team`` checks only the
  datasets added by this save. A refusal is 409 ``assistant_dataset_not_shared`` and names the offenders the caller can open.
* Chat time (D-25, per reader). The usable set is the bound ids that still exist and that the asker can open; the rest are counted as
  unavailable. The assistant's own permission is not consulted, because chats are private to the reader (D-11): a dataset that went private is
  skipped for everyone who cannot open it and kept for the one who can.
* Saving (D-25). The ids stored on the row that exist but that the saver cannot open are kept, and only the saver's visible ids are replaced by
  the requested list. A bound dataset that was deleted is dropped on the next save that sends ``kb_ids`` (there is nothing left to unbind).
* Narrowing ``team`` to ``me`` (D-23) is refused with 409 ``assistant_has_member_chats`` and ``data.count`` while any member other than the
  creator has a session with it. Nothing is deleted by a visibility change.
* Managing (D-24): the creator, and an owner or admin for a ``team`` assistant only (``tenant_scope.can_manage_assistant``; decided by the
  permission subject, so a token is not elevated). A visible assistant the caller cannot manage is ``FORBIDDEN`` on update and delete.
* Deleting (D-26) is a hard delete of the assistant and of every member's sessions with it, in one transaction.

Every write that changes an assistant takes its row ``FOR UPDATE`` inside a transaction; plan 05-09 takes the same lock when it creates a
session, so a narrowing and a session creation are serialised. Names are unique per workspace, case-insensitively, under the named lock
``dialog-create:{tenant_id}``. Model services open and close their own connection scope, so they run before ours, and no function here calls
into code that opens one while a scope of ours is open.

This module imports no web framework. Messages in ``ServiceError`` never hold a host, a key, SQL or the caller's input.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

import peewee

from api.db.database import DB, DatabaseLock, LockError, LockTimeoutError, transaction
from api.db.models import Conversation, Dialog
from api.db.services import tenant_model_service
from api.db.services.auth_service import Principal
from api.db.services.dialog_datasets import live_datasets, requested_datasets, require_shareable, usable_ids
from api.db.services.dialog_records import AssistantRecord, VisibleAssistant, assistant_view, record_of
from api.db.services.dialog_rules import (
    DEFAULT_LLM_SETTING,
    DEFAULT_PROMPT_CONFIG,
    DEFAULT_SIMILARITY_THRESHOLD,
    DEFAULT_TOP_N,
    DEFAULT_VECTOR_SIMILARITY_WEIGHT,
    MAX_PAGE_SIZE,
    is_id,
    merge_prompt_config,
    sanitize_llm_setting,
    validate_fields,
)
from api.db.services.service_errors import Kind, ServiceError
from api.db.services.tenant_scope import PERMISSION_ME, PERMISSION_TEAM, ActingScope, assistant_visible, can_manage_assistant, scope_for_tenant
from api.utils import reasons
from common.model_ref import InvalidModelRef, parse_model_ref

__all__ = [
    "AssistantRecord",
    "VisibleAssistant",
    "assistant_view",
    "create_assistant",
    "delete_assistant",
    "get_assistant",
    "list_assistants",
    "load_visible_assistant",
    "sanitize_llm_setting",
]

logger = logging.getLogger(__name__)

LOCK_PREFIX = "dialog-create:"
LOCK_TIMEOUT_SECONDS = 10
_VALID = "1"  # dialog.status and knowledgebase.status: 1 is a live row


def _not_found() -> ServiceError:
    return ServiceError(Kind.NOT_FOUND, reasons.ASSISTANT_NOT_FOUND, "not found")


def dataset_not_found() -> ServiceError:
    return ServiceError(Kind.NOT_FOUND, reasons.DATASET_NOT_FOUND, "not found")


def _forbidden() -> ServiceError:
    return ServiceError(Kind.FORBIDDEN, reasons.FORBIDDEN, "forbidden")


def lock_name(tenant_id: str) -> str:
    """``dialog-create:`` plus a 32-character tenant id: 46 characters, within the 64 MySQL allows."""
    return f"{LOCK_PREFIX}{tenant_id}"


@contextmanager
def _named_lock(name: str, busy_message: str) -> Iterator[None]:
    lock = DatabaseLock(name, LOCK_TIMEOUT_SECONDS)
    try:
        lock.acquire()
    except (LockTimeoutError, LockError):
        raise ServiceError(Kind.UNAVAILABLE, reasons.BUSY, busy_message) from None
    try:
        yield
    finally:
        try:
            lock.release()
        except LockError:
            logger.warning("lock was not held at release name=%s", name)


# ----------------------------------------------------------------------------- records and datasets


def _members_with_chats(chat_id: str, excluded_user_id: str) -> int:
    """Distinct users other than ``excluded_user_id`` with at least one session of the assistant. Needs an open connection scope."""
    count = (
        Conversation.select(peewee.fn.COUNT(peewee.fn.DISTINCT(Conversation.user_id)))
        .where((Conversation.dialog_id == chat_id) & Conversation.user_id.is_null(False) & (Conversation.user_id != excluded_user_id))
        .scalar()
    )
    return int(count or 0)


# ----------------------------------------------------------------------------- views


def _detail(record: AssistantRecord, user_id: str, subject: str) -> dict[str, Any]:
    """The detail view for a reader. Needs an open connection scope."""
    usable = usable_ids(record.tenant_id, user_id, record.kb_ids, live_datasets(record.kb_ids))
    members = _members_with_chats(record.id, user_id) if can_manage_assistant(record.created_by, record.permission, user_id, subject) else None
    return assistant_view(record, usable_ids=usable, include_icon=True, members_with_chats=members)


# ----------------------------------------------------------------------------- loading and authorising


def load_visible_assistant(principal: Principal, chat_id: str) -> VisibleAssistant:
    """The assistant and the caller's scope in its workspace, or the one ``NOT_FOUND`` for an absent, foreign or private-to-someone-else one."""
    if not is_id(chat_id):
        raise _not_found()
    with DB.connection_context():
        row = Dialog.get_or_none((Dialog.id == chat_id) & (Dialog.status == _VALID))
    if row is None:
        raise _not_found()
    scope = scope_for_tenant(principal, row.tenant_id)  # opens its own connection scope: called after ours is closed
    if scope is None or not assistant_visible(row.created_by, row.permission, principal.user_id, True):
        raise _not_found()
    return VisibleAssistant(record_of(row), scope)


def _require_manage(creator_id: str, permission: str, user_id: str, scope: ActingScope) -> None:
    if not can_manage_assistant(creator_id, permission, user_id, scope.subject):
        raise _forbidden()


def _recheck(row: Dialog, user_id: str, scope: ActingScope) -> None:
    """After taking the row lock: the assistant may have been narrowed, re-shared or deleted since it was first read."""
    if not assistant_visible(row.created_by, row.permission, user_id, True):
        raise _not_found()
    _require_manage(row.created_by, row.permission, user_id, scope)


def _name_taken(tenant_id: str, name: str, exclude_id: str | None = None) -> bool:
    same = (Dialog.name == name) | (peewee.fn.LOWER(Dialog.name) == name.lower())
    where = (Dialog.tenant_id == tenant_id) & (Dialog.status == _VALID) & same
    if exclude_id is not None:
        where = where & (Dialog.id != exclude_id)
    return Dialog.select(Dialog.id).where(where).first() is not None


def _model(tenant_id: str, wanted: str, model_type: str) -> tenant_model_service.ModelInfo:
    """A model of the workspace of the given type, or ``model_unavailable``. Opens its own connection scope."""
    unavailable = ServiceError(Kind.INVALID, reasons.MODEL_UNAVAILABLE, "that model is not available in this workspace")
    try:
        ref = parse_model_ref(wanted)
    except InvalidModelRef:
        raise unavailable from None
    found = tenant_model_service.find_model(tenant_id, ref)
    if found is None or found.model_type != model_type:
        raise unavailable
    return found


def _model_columns(tenant_id: str, patch: Mapping[str, Any], current: AssistantRecord | None) -> dict[str, Any]:
    """Column values for ``llm_id`` and ``rerank_id`` when the patch changes them; each is checked against the workspace's models."""
    values: dict[str, Any] = {}
    if "llm_id" in patch and (current is None or patch["llm_id"] != current.llm_id):
        chat = _model(tenant_id, patch["llm_id"], "chat")
        values.update(llm_id=chat.composite, tenant_llm_id=chat.id)
    if "rerank_id" in patch and (current is None or patch["rerank_id"] != current.rerank_id):
        if patch["rerank_id"]:
            rerank = _model(tenant_id, patch["rerank_id"], "rerank")
            values.update(rerank_id=rerank.composite, tenant_rerank_id=rerank.id)
        else:
            values.update(rerank_id="", tenant_rerank_id=None)
    elif current is None:
        values.update(rerank_id="", tenant_rerank_id=None)
    return values


# ----------------------------------------------------------------------------- binding rules (D-10, D-25)


# ----------------------------------------------------------------------------- create


def _new_values(patch: Mapping[str, Any], models: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": patch["name"],
        "icon": patch.get("icon") or None,
        "permission": patch.get("permission", PERMISSION_ME),
        "similarity_threshold": patch.get("similarity_threshold", DEFAULT_SIMILARITY_THRESHOLD),
        "vector_similarity_weight": patch.get("vector_similarity_weight", DEFAULT_VECTOR_SIMILARITY_WEIGHT),
        "top_n": patch.get("top_n", DEFAULT_TOP_N),
        "prompt_config": merge_prompt_config(patch.get("prompt_config", {}), DEFAULT_PROMPT_CONFIG),
        "llm_setting": sanitize_llm_setting(patch.get("llm_setting"), DEFAULT_LLM_SETTING),
        **models,
    }


def create_assistant(principal: Principal, scope: ActingScope, body: Mapping[str, Any]) -> dict[str, Any]:
    """Create an assistant in the acting workspace for the caller and return its detail view. See the module note for the rules."""
    patch = validate_fields(body, creating=True)
    tenant_id, user_id = scope.tenant_id, principal.user_id
    models = _model_columns(tenant_id, patch, None)  # before our connection scope: the model services open and close their own
    requested: list[str] = patch.get("kb_ids", [])
    values = _new_values(patch, models)
    chat_id = uuid.uuid4().hex
    with _named_lock(lock_name(tenant_id), "another assistant is being saved, try again shortly"), DB.connection_context():
        known = requested_datasets(requested, tenant_id, user_id)
        if values["permission"] == PERMISSION_TEAM:
            require_shareable(requested, known, tenant_id, user_id)
        if _name_taken(tenant_id, values["name"]):
            raise ServiceError(Kind.CONFLICT, reasons.DUPLICATE_NAME, "an assistant with that name already exists")
        with transaction():
            row = Dialog.create(id=chat_id, tenant_id=tenant_id, created_by=user_id, kb_ids=requested, status=_VALID, **values)
        view = _detail(record_of(row), user_id, scope.subject)
    logger.info("assistant created tenant=%s assistant=%s permission=%s datasets=%d", tenant_id, chat_id, values["permission"], len(requested))
    return view


# ----------------------------------------------------------------------------- list and read


def _like(text: str) -> str:
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def list_assistants(principal: Principal, scope: ActingScope, page: int, page_size: int, keywords: str | None = None) -> tuple[list[dict[str, Any]], int]:
    """One page of the assistants the caller may see (their own and every ``team`` one), newest first, as list views without ``icon``, and the total."""
    page = max(1, int(page))
    page_size = min(max(1, int(page_size)), MAX_PAGE_SIZE)
    user_id = principal.user_id
    where = (Dialog.tenant_id == scope.tenant_id) & (Dialog.status == _VALID) & ((Dialog.created_by == user_id) | (Dialog.permission == PERMISSION_TEAM))
    if keywords:
        where = where & peewee.NodeList((Dialog.name, peewee.SQL("LIKE"), _like(keywords), peewee.SQL("ESCAPE '\\\\'")))
    columns = [field for field in Dialog._meta.sorted_fields if field is not Dialog.icon]  # a data-URL icon can be 400 kB: never loaded for a list
    with DB.connection_context():
        total = Dialog.select().where(where).count()
        records = [record_of(r, with_icon=False) for r in Dialog.select(*columns).where(where).order_by(Dialog.update_time.desc(), Dialog.id).paginate(page, page_size)]
        known = live_datasets(i for r in records for i in r.kb_ids)  # one query for the whole page
        items = [assistant_view(r, usable_ids=usable_ids(r.tenant_id, user_id, r.kb_ids, known), include_icon=False) for r in records]
    return items, total


def get_assistant(principal: Principal, chat_id: str) -> dict[str, Any]:
    """The detail view for the caller, or the one ``NOT_FOUND``. ``members_with_chats`` is present only for a caller who can manage the assistant."""
    visible = load_visible_assistant(principal, chat_id)
    with DB.connection_context():
        return _detail(visible.assistant, principal.user_id, visible.scope.subject)


# ----------------------------------------------------------------------------- delete


def delete_assistant(principal: Principal, chat_id: str) -> str:
    """Hard-delete the assistant and every member's sessions with it in one transaction (D-26); returns the id.

    The creator may delete any of their assistants; an owner or admin only a ``team`` one. A visible assistant the caller cannot manage is ``FORBIDDEN``.
    """
    visible = load_visible_assistant(principal, chat_id)
    current, scope, user_id = visible.assistant, visible.scope, principal.user_id
    _require_manage(current.created_by, current.permission, user_id, scope)
    with DB.connection_context(), transaction():
        row = Dialog.select().where((Dialog.id == chat_id) & (Dialog.status == _VALID)).for_update().first()
        if row is None:
            raise _not_found()
        _recheck(row, user_id, scope)
        removed = Conversation.delete().where(Conversation.dialog_id == chat_id).execute()
        Dialog.delete().where(Dialog.id == chat_id).execute()
    logger.info("assistant deleted tenant=%s assistant=%s sessions=%d", current.tenant_id, chat_id, removed)
    return chat_id
