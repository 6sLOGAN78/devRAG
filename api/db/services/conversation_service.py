"""Per-user chat sessions, message persistence and turn guards (plan 05-09)."""
from __future__ import annotations

import datetime as dt
import re
import uuid
from typing import Any

import valkey
from valkey.exceptions import LockError, ValkeyError
from valkey.lock import Lock

from api.db.database import DB, transaction
from api.db.models import Conversation, Dialog
from api.db.services.auth_service import Principal
from api.db.services.conversation_redaction import redact_messages
from api.db.services.dialog_rules import is_id
from api.db.services.dialog_service import load_visible_assistant
from api.db.services.service_errors import Kind, ServiceError
from api.db.services.tenant_scope import assistant_visible
from api.utils import reasons
from common.ratelimit import FixedWindowLimiter, RateLimited, RateLimitUnavailable
from common.settings import ChatSettings, Settings, get_settings

_LIVE = "1"
_SPACE = re.compile(r"\s+")


def _not_found() -> ServiceError:
    return ServiceError(Kind.NOT_FOUND, reasons.ASSISTANT_NOT_FOUND, "not found")


def _invalid(message: str) -> ServiceError:
    return ServiceError(Kind.INVALID, reasons.FIELDS_INVALID, message)


def _session(chat_id: str, session_id: str, user_id: str, *, locked: bool = False) -> Conversation:
    if not is_id(session_id):
        raise _not_found()
    query = Conversation.select().where(
        (Conversation.id == session_id) & (Conversation.dialog_id == chat_id) & (Conversation.user_id == user_id)
    )
    row = (query.for_update() if locked else query).first()
    if row is None:
        raise _not_found()
    return row


def _summary(row: Conversation) -> dict[str, Any]:
    return {
        "id": row.id,
        "chat_id": row.dialog_id,
        "name": row.name or "",
        "create_time": int(row.create_time or 0),
        "update_time": int(row.update_time or 0),
    }


def _page(row: Conversation, before: str | None, limit: int, tenant_id: str, user_id: str) -> dict[str, Any]:
    messages = row.message if isinstance(row.message, list) else []
    if before is not None:
        if not is_id(before):
            raise _not_found()
        try:
            end = next(i for i, message in enumerate(messages) if isinstance(message, dict) and message.get("id") == before)
        except StopIteration:
            raise _not_found() from None
    else:
        end = len(messages)
    start = max(0, end - limit)
    selected = [m for m in messages[start:end] if isinstance(m, dict)]
    return {**_summary(row), "messages": redact_messages(selected, tenant_id, user_id), "has_earlier": start > 0}


def create_session(principal: Principal, chat_id: str, name: str | None = None) -> dict[str, Any]:
    visible = load_visible_assistant(principal, chat_id)
    if name is not None and (not isinstance(name, str) or len(name) > 255):
        raise _invalid("session name must be at most 255 characters")
    with DB.connection_context(), transaction():
        assistant = Dialog.select().where((Dialog.id == chat_id) & (Dialog.status == _LIVE)).for_update().first()
        if assistant is None or not assistant_visible(assistant.created_by, assistant.permission, principal.user_id, True):
            raise _not_found()
        row = Conversation.create(id=uuid.uuid4().hex, dialog_id=chat_id, user_id=principal.user_id, name=name or "", message=[], reference=[])
        return _page(row, None, 50, visible.scope.tenant_id, principal.user_id)


def list_sessions(principal: Principal, chat_id: str, page: int = 1, page_size: int = 20) -> dict[str, Any]:
    load_visible_assistant(principal, chat_id)
    if not 1 <= page <= 1000000 or not 1 <= page_size <= 100:
        raise _invalid("invalid page or page_size")
    with DB.connection_context():
        query = Conversation.select().where((Conversation.dialog_id == chat_id) & (Conversation.user_id == principal.user_id))
        total = query.count()
        rows = list(query.order_by(Conversation.update_time.desc(), Conversation.id.desc()).paginate(page, page_size))
    return {"items": [_summary(row) for row in rows], "total": total}


def get_session(principal: Principal, chat_id: str, session_id: str, before: str | None = None, limit: int | None = None) -> dict[str, Any]:
    visible = load_visible_assistant(principal, chat_id)
    size = limit if limit is not None else get_settings().chat.message_page_size
    if not isinstance(size, int) or not 1 <= size <= 200:
        raise _invalid("limit must be between 1 and 200")
    with DB.connection_context():
        row = _session(chat_id, session_id, principal.user_id)
        return _page(row, before, size, visible.scope.tenant_id, principal.user_id)


def delete_session(principal: Principal, chat_id: str, session_id: str) -> dict[str, str]:
    load_visible_assistant(principal, chat_id)
    with DB.connection_context(), transaction():
        row = _session(chat_id, session_id, principal.user_id, locked=True)
        row.delete_instance()
    return {"deleted": session_id}


def set_feedback(principal: Principal, chat_id: str, session_id: str, message_id: str, thumb: str | None, comment: str | None = None) -> dict[str, Any]:
    load_visible_assistant(principal, chat_id)
    if thumb not in ("up", "down", None) or (comment is not None and (not isinstance(comment, str) or len(comment) > 500)):
        raise _invalid("invalid feedback")
    if not is_id(message_id):
        raise _not_found()
    with DB.connection_context(), transaction():
        row = _session(chat_id, session_id, principal.user_id, locked=True)
        messages = list(row.message or [])
        for i, message in enumerate(messages):
            if isinstance(message, dict) and message.get("id") == message_id and message.get("role") == "assistant" and message.get("finish") == "complete":
                messages[i] = {**message, "feedback": thumb}
                if comment is not None:
                    messages[i]["feedback_comment"] = comment
                row.message = messages
                row.save()
                return {"message_id": message_id, "feedback": thumb}
    raise _not_found()


class TurnLock:
    """Owner checked Valkey lock; a lost lock cannot delete another turn's key."""

    def __init__(self, client: valkey.Valkey, lock: Lock, key: str) -> None:
        self._client, self._lock, self.key = client, lock, key

    def ttl(self) -> int:
        try:
            return int(self._client.ttl(self.key))
        except (ValkeyError, OSError):
            raise ServiceError(Kind.UNAVAILABLE, reasons.BUSY, "chat store unavailable") from None

    def renew(self) -> None:
        """Reset this owner's lease before another bounded stage of the turn begins."""
        try:
            self._lock.reacquire()
        except LockError:
            raise ServiceError(Kind.CONFLICT, reasons.TURN_IN_PROGRESS, "the turn is no longer active") from None
        except (ValkeyError, OSError):
            raise ServiceError(Kind.UNAVAILABLE, reasons.BUSY, "chat store unavailable") from None

    def release(self) -> bool:
        try:
            self._lock.release()
            return True
        except LockError:
            return False
        except (ValkeyError, OSError):
            return False
        finally:
            self._client.close()

    def __enter__(self) -> TurnLock:
        return self

    def __exit__(self, *_: object) -> None:
        self.release()


def acquire_turn(settings: Settings, session_id: str) -> TurnLock:
    if not is_id(session_id):
        raise _not_found()
    rd = settings.redis
    client = valkey.Valkey(host=rd.host, port=rd.port, password=rd.password or None, db=rd.db, socket_timeout=2, socket_connect_timeout=2)
    key = f"chat_turn:{session_id}"
    lock = Lock(client, key, timeout=settings.chat.stream_deadline_seconds + 30, thread_local=False)
    try:
        acquired = lock.acquire(blocking=False)
    except (ValkeyError, OSError):
        client.close()
        raise ServiceError(Kind.UNAVAILABLE, reasons.BUSY, "chat store unavailable") from None
    if not acquired:
        client.close()
        raise ServiceError(Kind.CONFLICT, reasons.TURN_IN_PROGRESS, "a turn is already in progress")
    return TurnLock(client, lock, key)


def chat_rate_guard(settings: Settings, tenant_id: str, user_id: str) -> None:
    try:
        FixedWindowLimiter(settings.redis).hit(f"chat:{tenant_id}:{user_id}", settings.chat.rate_max, settings.chat.rate_window_seconds)
    except RateLimited as exc:
        raise ServiceError(Kind.RATE_LIMITED, "rate_limited", "chat rate limit reached", retry_after=exc.retry_after) from None
    except RateLimitUnavailable:
        raise ServiceError(Kind.UNAVAILABLE, reasons.BUSY, "chat store unavailable") from None


def _created_at() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def append_user_message(principal: Principal, chat_id: str, session_id: str, text: str, settings: ChatSettings) -> tuple[str, list[dict[str, Any]]]:
    load_visible_assistant(principal, chat_id)
    if not isinstance(text, str) or not text.strip() or len(text) > settings.max_question_chars:
        raise ServiceError(Kind.INVALID, reasons.QUESTION_INVALID, "question is empty or too long")
    with DB.connection_context(), transaction():
        row = _session(chat_id, session_id, principal.user_id, locked=True)
        history = list(row.message or [])
        if len(history) >= settings.max_session_messages:
            raise ServiceError(Kind.CONFLICT, reasons.SESSION_FULL, "session is full")
        message_id = uuid.uuid4().hex
        row.message = [*history, {"id": message_id, "role": "user", "content": text, "created_at": _created_at()}]
        if not row.name:
            row.name = _SPACE.sub(" ", text).strip()[:60]
        row.save()
    return message_id, history


def append_assistant_message(session_id: str, message_dict: dict[str, Any]) -> None:
    if not is_id(session_id) or not is_id(message_dict.get("id")) or message_dict.get("role") != "assistant":
        raise _invalid("invalid assistant message")
    with DB.connection_context(), transaction():
        row = Conversation.select().where(Conversation.id == session_id).for_update().first()
        if row is None:
            raise _not_found()
        row.message = [*(row.message or []), dict(message_dict)]
        row.save()


def replace_assistant_message(session_id: str, message_id: str, message_dict: dict[str, Any]) -> None:
    if not is_id(session_id) or not is_id(message_id) or message_dict.get("role") != "assistant":
        raise _invalid("invalid assistant message")
    with DB.connection_context(), transaction():
        row = Conversation.select().where(Conversation.id == session_id).for_update().first()
        if row is None:
            raise _not_found()
        messages = list(row.message or [])
        for i, message in enumerate(messages):
            if isinstance(message, dict) and message.get("id") == message_id and message.get("role") == "assistant":
                messages[i] = {**message_dict, "id": message_id}
                row.message = messages
                row.save()
                return
    raise _not_found()
