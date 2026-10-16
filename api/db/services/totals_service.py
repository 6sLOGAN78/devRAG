"""Document and dataset counters set to the truth of the index (plan 04-10; KB-19, R-159).

Workers never add to ``chunk_num`` or ``token_num``. After a task they call :func:`settle_totals`, which counts the document's chunks in the
index (and sums ``token_num_int``), writes those numbers to the document under a row lock and moves the dataset's totals by the difference. Calling
it twice, or after a crash, repairs drift instead of counting twice.
"""

from __future__ import annotations

import logging

import peewee

from api.db.database import DB, transaction
from api.db.models import Document, Knowledgebase
from api.db.models.base import current_timestamp_ms, timestamp_to_date
from api.db.services.service_errors import Kind, ServiceError
from api.utils import reasons
from common.doc_store.doc_store_base import DocStoreConnection, DocStoreError, index_name
from common.settings import Settings
from rag.utils.es_conn import get_doc_store

logger = logging.getLogger(__name__)

DEADLOCK_ATTEMPTS = 3
_MYSQL_DEADLOCK = 1213


def settle_totals(settings: Settings, tenant_id: str, dataset_id: str, doc_id: str, *, doc_store: DocStoreConnection | None = None) -> tuple[int, int]:
    """Set the document's ``chunk_num`` and ``token_num`` from the index and move the dataset by the difference. Returns ``(chunks, tokens)``."""
    engine = doc_store if doc_store is not None else get_doc_store(settings)
    try:
        found = engine.stats({"doc_id": [doc_id]}, index_name(tenant_id), dataset_id, sum_field="token_num_int")
    except DocStoreError as exc:
        logger.warning("settle_totals could not read the index tenant=%s dataset=%s error=%s", tenant_id, dataset_id, type(exc).__name__)
        raise ServiceError(Kind.UNAVAILABLE, reasons.INDEX_UNAVAILABLE, "the search index is not available, try again shortly") from None
    chunks, tokens = int(found.count), int(found.total)
    for attempt in range(1, DEADLOCK_ATTEMPTS + 1):
        try:
            with DB.connection_context(), transaction():
                row = Document.select(Document.chunk_num, Document.token_num).where((Document.id == doc_id) & (Document.kb_id == dataset_id)).for_update().first()
                if row is None:
                    return chunks, tokens  # the document is gone: nothing to settle
                delta_chunks = chunks - int(row.chunk_num or 0)
                delta_tokens = tokens - int(row.token_num or 0)
                now = current_timestamp_ms()
                stamp = {"update_time": now, "update_date": timestamp_to_date(now)}
                Document.update(chunk_num=chunks, token_num=tokens, **stamp).where(Document.id == doc_id).execute()
                if delta_chunks or delta_tokens:
                    Knowledgebase.update(
                        chunk_num=peewee.fn.GREATEST(Knowledgebase.chunk_num + delta_chunks, 0),
                        token_num=peewee.fn.GREATEST(Knowledgebase.token_num + delta_tokens, 0),
                        **stamp,
                    ).where(Knowledgebase.id == dataset_id).execute()
            return chunks, tokens
        except peewee.OperationalError as exc:
            if exc.args and exc.args[0] == _MYSQL_DEADLOCK and attempt < DEADLOCK_ATTEMPTS:
                logger.warning("settle_totals was a deadlock victim dataset=%s attempt=%d", dataset_id, attempt)
                continue
            raise
    raise AssertionError("unreachable: the last attempt returns or raises")
