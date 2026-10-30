"""Authorized, bounded current-source tag inventory and checked association deletion."""
from collections import Counter
import re
import time

from api.db.database import DB
from api.db.models import Document
from api.db.services.knowledgebase_service import load_visible_dataset, _require_manage, _named_lock, upload_lock_name
from api.db.services.service_errors import Kind, ServiceError
from api.utils import reasons
from common.doc_store.doc_store_base import DocStoreError, OrderByExpr, index_name
from rag.parsers.tags import TAG_FIELD, TAG_LABEL_FIELD, normalize_tags, tag_label
from rag.utils.es_conn import get_doc_store

_ID=re.compile(r"[0-9a-f]{32}")
MAX_ROWS=10000
MAX_LABELS=512
DEADLINE_SECONDS=30


def _invalid():
    return ServiceError(Kind.INVALID,reasons.FIELDS_INVALID,"the tag selection is not valid")


def _unavailable():
    return ServiceError(Kind.UNAVAILABLE,reasons.INDEX_UNAVAILABLE,"the search index is not available, try again shortly")


def _ids(ids):
    if not isinstance(ids,list) or not 1<=len(ids)<=32 or any(not isinstance(v,str) or _ID.fullmatch(v) is None for v in ids) or len(set(ids))!=len(ids):
        raise _invalid()
    return ids


def _deadline(started):
    if time.monotonic()-started>DEADLINE_SECONDS:
        raise ServiceError(Kind.UNAVAILABLE,reasons.BUSY,"the tag operation took too long, try again shortly")


def _inventory(engine,visible,remaining,started,*,include_disabled=False):
    with DB.connection_context():
        query=Document.select(Document.id).where(Document.kb_id==visible.dataset.id).order_by(Document.id)
        if not include_disabled:
            query=query.where(Document.status=="1")
        docs=[doc.id for doc in query.limit(MAX_ROWS+1)]
    if len(docs)>MAX_ROWS:
        raise ServiceError(Kind.CONFLICT,reasons.FIELDS_INVALID,"too many documents for this tag operation")
    if not docs:
        return []
    doc_ids=set(docs)
    condition={"doc_id":docs,"must_not":{"removed_kwd":"Y"}}
    if not include_disabled:
        condition.update(available_int=1,doc_enabled_int=1)
    tenant=visible.scope.tenant_id
    _deadline(started)
    total=engine.search([],[],condition,[],None,0,0,index_name(tenant),[visible.dataset.id]).total
    if total>remaining:
        raise ServiceError(Kind.CONFLICT,reasons.FIELDS_INVALID,"too many indexed chunks for this tag operation")
    rows=[]
    for offset in range(0,total,500):
        _deadline(started)
        result=engine.search([TAG_FIELD,TAG_LABEL_FIELD,"doc_id","task_id"],[],condition,[],OrderByExpr().asc("id"),offset,500,index_name(tenant),[visible.dataset.id])
        if result.total>remaining or len(rows)+len(result.hits)>remaining:
            raise ServiceError(Kind.CONFLICT,reasons.FIELDS_INVALID,"too many indexed chunks for this tag operation")
        rows.extend(row for row in result.hits if row.get("doc_id") in doc_ids)
    return rows


def _summarize(rows):
    totals=Counter()
    counts=Counter()
    for row in rows:
        weights=normalize_tags(row.get(TAG_FIELD) or {})
        for label,weight in weights.items():
            totals[label]+=weight
            counts[label]+=1
            if len(totals)>MAX_LABELS:
                raise ServiceError(Kind.CONFLICT,reasons.FIELDS_INVALID,"too many tags to display; reduce the selected datasets")
    weights=normalize_tags(dict(totals),limit=MAX_LABELS)
    items=[{"tag":label,"weight":weight,"count":counts[label]} for label,weight in weights.items()]
    items.sort(key=lambda item:(-item["weight"],item["tag"]))
    return {"items":items,"total":len(items)}


def aggregate_tags(settings,principal,ids,*,doc_store=None):
    ids=_ids(ids)
    visible=[load_visible_dataset(principal,value) for value in ids]  # All authorization precedes any index read.
    engine=doc_store if doc_store is not None else get_doc_store(settings)
    started=time.monotonic()
    rows=[]
    try:
        for dataset in visible:
            rows.extend(_inventory(engine,dataset,MAX_ROWS-len(rows),started))
        result=_summarize(rows)
    except (DocStoreError,ValueError,TypeError):
        raise _unavailable() from None
    for value in ids:
        load_visible_dataset(principal,value)  # Current visibility again before publication.
    return result


def list_tags(settings,principal,dataset_id,*,doc_store=None):
    return aggregate_tags(settings,principal,[dataset_id],doc_store=doc_store)


def delete_tags(settings,principal,dataset_id,labels,*,doc_store=None):
    _ids([dataset_id])
    if not isinstance(labels,list) or not 1<=len(labels)<=128:
        raise _invalid()
    try:
        selected=sorted({tag_label(label) for label in labels})
    except ValueError:
        raise _invalid() from None
    visible=load_visible_dataset(principal,dataset_id)
    _require_manage(visible,principal.user_id)
    engine=doc_store if doc_store is not None else get_doc_store(settings)
    started=time.monotonic()
    with _named_lock(upload_lock_name(dataset_id),10,"another change to this dataset is running, try again shortly"):
        visible=load_visible_dataset(principal,dataset_id)
        _require_manage(visible,principal.user_id)
        with DB.connection_context():
            running=Document.select(Document.id).where((Document.kb_id==dataset_id)&(Document.run=="1")).exists()
        if running:
            raise ServiceError(Kind.CONFLICT,reasons.PARSE_RUNNING,"wait for parsing to finish before deleting tags")
        deleted=set()
        count=0
        try:
            rows=_inventory(engine,visible,MAX_ROWS,started,include_disabled=True)
            for row in rows:
                _deadline(started)
                before=normalize_tags(row.get(TAG_FIELD) or {})
                removed=set(before).intersection(selected)
                if not removed:
                    continue
                after=normalize_tags({key:value for key,value in before.items() if key not in removed})
                condition={"id":[row["id"]],"doc_id":[row["doc_id"]],"task_id":[row.get("task_id","")]}
                done=engine.update(condition,{TAG_FIELD:after,TAG_LABEL_FIELD:list(after)},index_name(visible.scope.tenant_id),dataset_id)
                if not done:
                    raise _unavailable()
                deleted.update(removed)
                count+=1
        except (DocStoreError,ValueError,TypeError,KeyError):
            raise _unavailable() from None
    return {"deleted":sorted(deleted),"count":count}
