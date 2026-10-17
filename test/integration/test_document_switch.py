"""The document search switch against the real MySQL and Elasticsearch (plan 04-17; DOC-13, IDX-14, D-26, R-163).

A document switch is stored in ``document.status`` and written to ``doc_enabled_int`` on every chunk of the document; a chunk's own
``available_int`` is never touched, so switching a document back on restores exactly what was searchable before.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from api.db.services import document_service as docs
from api.db.services.auth_service import AUTH_API, Principal
from api.db.services.service_errors import Kind
from common.doc_store.doc_store_base import DocStoreError, index_name
from rag.utils.es_conn import get_doc_store
from test.helpers.doc_store_contract import DIM, row, search
from test.helpers.uploads import pdf_bytes, sql
from test.integration.test_document_service import team_dataset_of
from test.integration.test_knowledgebase_service import configure, join, make, principal_of
from test.integration.test_upload_service import FaultyStorage, _bound_database, item, llm, refused, registry, settings, space, upload  # noqa: F401

pytestmark = pytest.mark.integration


class DownIndex:
    """A document store whose update fails the way an unreachable index does."""

    def update(self, *args: Any, **kwargs: Any) -> bool:
        raise DocStoreError("index down")


def put(cfg, owner, dataset, doc_id: str, count: int, *, unavailable: tuple[int, ...] = ()) -> list[str]:
    rows = []
    for i in range(count):
        made = row(uuid.uuid4().hex, doc_id, f"chunk {i} of {doc_id}", i % DIM, i)
        made["available_int"] = 0 if i in unavailable else 1
        made["doc_enabled_int"] = 1
        rows.append(made)
    store = get_doc_store(cfg)
    store.create_idx(index_name(owner.tenant_id), dataset.id, DIM, "naive")
    assert store.insert(rows, index_name(owner.tenant_id), dataset.id) == []
    return [r["id"] for r in rows]


def flags(cfg, owner, dataset, doc_id: str) -> list[tuple[int, int]]:
    result = search(
        get_doc_store(cfg), index_name(owner.tenant_id), [dataset.id], condition={"doc_id": [doc_id]}, select=["available_int", "doc_enabled_int"], limit=100
    )
    return sorted((int(h["available_int"]), int(h["doc_enabled_int"])) for h in result.hits)


def stored_status(doc_id: str) -> str:
    return str(sql("SELECT `status` FROM `document` WHERE `id` = %s", (doc_id,))[0][0])


def switch(cfg, who, dataset, ids, enabled: bool, **kw: Any) -> list[str]:
    visible = docs.authorize_removal(principal_of(who), dataset.id)
    return docs.set_documents_enabled(cfg, visible, principal_of(who), ids, enabled, **kw)


def made_document(cfg, owner, dataset, name: str, chunks: int = 5, **kw: Any) -> str:
    doc_id = upload(cfg, owner, dataset, [item(name, pdf_bytes(name))], storage=FaultyStorage(cfg))[0]["id"]
    put(cfg, owner, dataset, doc_id, chunks, **kw)
    return doc_id


def test_off_and_on_keep_each_chunks_own_choice(settings, space):
    owner, dataset = space
    doc_id = made_document(settings, owner, dataset, "a.pdf", unavailable=(2,))
    assert flags(settings, owner, dataset, doc_id) == [(0, 1), (1, 1), (1, 1), (1, 1), (1, 1)]

    assert switch(settings, owner, dataset, [doc_id], False) == [doc_id]
    assert flags(settings, owner, dataset, doc_id) == [(0, 0), (1, 0), (1, 0), (1, 0), (1, 0)], "available_int is left as it was"
    assert stored_status(doc_id) == "0"

    assert switch(settings, owner, dataset, [doc_id], True) == [doc_id]
    assert flags(settings, owner, dataset, doc_id) == [(0, 1), (1, 1), (1, 1), (1, 1), (1, 1)], "the one chunk that was off is still off"
    assert stored_status(doc_id) == "1"


def test_only_the_listed_documents_change(settings, space):
    owner, dataset = space
    first = made_document(settings, owner, dataset, "first.pdf", 3)
    second = made_document(settings, owner, dataset, "second.pdf", 3)
    switch(settings, owner, dataset, [first], False)
    assert {f[1] for f in flags(settings, owner, dataset, first)} == {0}
    assert {f[1] for f in flags(settings, owner, dataset, second)} == {1}
    assert stored_status(second) == "1"


def test_one_foreign_id_changes_nothing_and_is_the_one_not_found(settings, space, registry, llm):
    owner, dataset = space
    mine = made_document(settings, owner, dataset, "mine.pdf", 3)
    other = registry.register(prefix="swfor")
    configure(llm, other)
    theirs_dataset = make(settings, other)
    theirs = made_document(settings, other, theirs_dataset, "theirs.pdf", 3)
    err = refused(lambda: switch(settings, owner, dataset, [mine, theirs], False))
    assert err.kind is Kind.NOT_FOUND
    assert stored_status(mine) == "1" and stored_status(theirs) == "1"
    assert {f[1] for f in flags(settings, owner, dataset, mine)} == {1}
    assert {f[1] for f in flags(settings, other, theirs_dataset, theirs)} == {1}


def test_a_member_who_is_not_the_uploader_or_creator_is_forbidden(settings, llm, registry):
    owner, creator, writer, plain = (registry.register(prefix=p) for p in ("swown", "swcre", "swwri", "swpla"))
    configure(llm, owner)
    for member in (creator, writer, plain):
        join(owner, member)
    dataset = team_dataset_of(settings, owner, creator)
    doc_id = made_document(settings, writer, dataset, "w.pdf", 2)
    assert refused(lambda: switch(settings, plain, dataset, [doc_id], False)).kind is Kind.FORBIDDEN
    assert stored_status(doc_id) == "1" and {f[1] for f in flags(settings, writer, dataset, doc_id)} == {1}
    assert switch(settings, writer, dataset, [doc_id], False) == [doc_id], "the uploader"
    assert switch(settings, creator, dataset, [doc_id], True) == [doc_id], "the dataset's creator"
    assert switch(settings, owner, dataset, [doc_id], False) == [doc_id], "the workspace owner"


def test_a_token_is_judged_as_its_subject_and_not_elevated(settings, llm, registry):
    owner, creator, writer = (registry.register(prefix=p) for p in ("swtow", "swtcr", "swtwr"))
    configure(llm, owner)
    join(owner, creator)
    join(owner, writer)
    dataset = team_dataset_of(settings, owner, creator)
    doc_id = made_document(settings, writer, dataset, "t.pdf", 2)
    token = Principal(owner.user_id, owner.tenant_id, "owner", AUTH_API, False)
    visible = docs.authorize_removal(token, dataset.id)
    err = refused(lambda: docs.set_documents_enabled(settings, visible, token, [doc_id], False))
    assert err.kind is Kind.FORBIDDEN
    assert stored_status(doc_id) == "1"


def test_an_unreachable_index_reverts_the_stored_switch_and_is_503(settings, space):
    owner, dataset = space
    doc_id = made_document(settings, owner, dataset, "down.pdf", 3)
    err = refused(lambda: switch(settings, owner, dataset, [doc_id], False, doc_store=DownIndex()))
    assert err.kind is Kind.UNAVAILABLE and err.reason == "index_unavailable"
    assert stored_status(doc_id) == "1", "the stored switch was restored"
    assert {f[1] for f in flags(settings, owner, dataset, doc_id)} == {1}


def test_ids_must_be_well_formed_and_not_empty(settings, space):
    owner, dataset = space
    assert refused(lambda: switch(settings, owner, dataset, [], False)).reason == "ids_invalid"
    assert refused(lambda: switch(settings, owner, dataset, ["nope"], False)).reason == "ids_invalid"


def test_a_document_without_chunks_can_be_switched(settings, space):
    owner, dataset = space
    doc_id = upload(settings, owner, dataset, [item("empty.pdf", pdf_bytes("empty"))], storage=FaultyStorage(settings))[0]["id"]
    assert switch(settings, owner, dataset, [doc_id], False) == [doc_id]
    assert stored_status(doc_id) == "0"
