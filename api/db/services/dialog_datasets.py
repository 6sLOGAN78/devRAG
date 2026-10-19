"""Dataset facts an assistant binding depends on (plan 05-07; D-10, D-25).

Everything here needs an open connection scope of the caller and opens none itself, because a nested scope would close the caller's.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from api.db.models import Knowledgebase
from api.db.services.service_errors import Kind, ServiceError
from api.db.services.tenant_scope import PERMISSION_TEAM, dataset_visible
from api.utils import reasons

_VALID = "1"  # knowledgebase.status: 1 is a live dataset


@dataclass(frozen=True)
class Dataset:
    id: str
    tenant_id: str
    created_by: str
    permission: str
    embd_id: str


def dataset_not_found() -> ServiceError:
    return ServiceError(Kind.NOT_FOUND, reasons.DATASET_NOT_FOUND, "not found")


def live_datasets(ids: Iterable[str]) -> dict[str, Dataset]:
    """The live datasets among ``ids`` (a deleted or wasted dataset is simply absent). Needs an open connection scope."""
    wanted = list(dict.fromkeys(ids))
    if not wanted:
        return {}
    rows = Knowledgebase.select(Knowledgebase.id, Knowledgebase.tenant_id, Knowledgebase.created_by, Knowledgebase.permission, Knowledgebase.embd_id).where(
        Knowledgebase.id.in_(wanted) & (Knowledgebase.status == _VALID)
    )
    return {r.id: Dataset(r.id, r.tenant_id, r.created_by, r.permission, r.embd_id) for r in rows}


def openable(dataset: Dataset, tenant_id: str, user_id: str) -> bool:
    """The dataset belongs to the assistant's workspace and the user may open it (``dataset_visible``)."""
    return dataset.tenant_id == tenant_id and dataset_visible(dataset.created_by, dataset.permission, user_id, True)


def usable_ids(tenant_id: str, user_id: str, ids: Sequence[str], known: Mapping[str, Dataset]) -> list[str]:
    return [i for i in ids if i in known and openable(known[i], tenant_id, user_id)]


def requested_datasets(requested: Sequence[str], tenant_id: str, user_id: str) -> dict[str, Dataset]:
    """Each requested dataset exists, is in the workspace and is openable by the saver (else ``dataset_not_found``); one embedding model. Needs a scope."""
    known = live_datasets(requested)
    if any(i not in known or not openable(known[i], tenant_id, user_id) for i in requested):
        raise dataset_not_found()
    if len({known[i].embd_id for i in requested}) > 1:
        raise ServiceError(Kind.INVALID, reasons.EMBEDDING_MISMATCH, "those datasets use different embedding models")
    return known


def require_shareable(ids: Sequence[str], known: Mapping[str, Dataset], tenant_id: str, user_id: str) -> None:
    """409 ``assistant_dataset_not_shared`` when a live dataset among ``ids`` is not ``team``; the offenders named are only ones the caller can open."""
    offenders = [known[i] for i in ids if i in known and known[i].permission != PERMISSION_TEAM]
    if offenders:
        shown = [d.id for d in offenders if openable(d, tenant_id, user_id)]
        raise ServiceError(
            Kind.CONFLICT, reasons.ASSISTANT_DATASET_NOT_SHARED, "a shared assistant can only use datasets that are shared with the team", data={"dataset_ids": shown}
        )
