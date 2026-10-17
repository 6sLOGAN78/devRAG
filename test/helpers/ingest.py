"""Shared builders for the ingestion pipeline tests (plan 04-11).

``paragraphs`` makes text whose chunk count is known from its arguments. ``make_pipeline_world`` creates a workspace whose embedding model points at
the loopback provider, a dataset, and helpers to upload a document, add task rows and run the pipeline against the real MySQL, MinIO and
Elasticsearch. The loopback provider is the other end of the wire, not a stub of devRag code.
"""

from __future__ import annotations

import dataclasses
import datetime
import io
import os
import time
import uuid
from base64 import urlsafe_b64encode
from dataclasses import dataclass
from typing import Any

from api.db.database import DB
from api.db.models import Task
from api.db.services import document_service as docs
from api.db.services import knowledgebase_service as kb
from api.db.services import tenant_model_service as structure
from api.db.services.document_service import UploadItem
from api.db.services.tenant_model_service import NewModel
from api.db.services.tenant_scope import ActingScope
from common.doc_store.doc_store_base import index_name
from common.model_ref import ModelRef
from common.settings import Settings, load_settings
from rag.nlp.token_count import count_tokens
from rag.svr.control import TaskControl
from rag.svr.embedding import EmbedRunner
from rag.svr.limiters import Limiters
from rag.svr.pipeline import PipelineDeps, PipelineResult, run_pipeline
from rag.utils.es_conn import get_doc_store
from rag.utils.storage_factory import get_storage
from test.helpers.accounts import Account, AccountRegistry
from test.helpers.doc_store_contract import search
from test.helpers.fake_provider import FakeProvider
from test.helpers.office_files import make_docx, make_html, make_pptx, make_xlsx, poison_docx  # noqa: F401  (re-exported)
from test.helpers.pdf_files import garbage_bytes, text_pdf, thirteen_page_pdf, truncated  # noqa: F401  (re-exported)
from test.helpers.uploads import sql
from test.integration.test_knowledgebase_service import principal_of

COMPAT = "OpenAI-API-Compatible"
DIMENSION = 8
EMBED_MODELS = (
    NewModel("fake-embed", "embedding", DIMENSION, 8192),
    NewModel("fake-filter", "embedding", DIMENSION, 8192),
    NewModel("fake-timeout", "embedding", DIMENSION, 8192),
    NewModel("fake-dim16", "embedding", 16, 8192),  # plan 04-19: the loopback answers 16 numbers for this name
)


def paragraph_text(i: int, tokens: int = 300) -> str:
    """One unique marker word followed by `` the`` until the paragraph is exactly ``tokens`` tokens."""
    text = f"para{i:04d}"
    while count_tokens(text) < tokens:
        text += " the"
    assert count_tokens(text) == tokens, "marker alone is longer than the requested size"
    return text


def paragraphs(n: int, tokens: int = 300) -> bytes:
    """``n`` paragraphs of exactly ``tokens`` tokens separated by blank lines; with the default budget each is one chunk."""
    return "\n\n".join(paragraph_text(i, tokens) for i in range(n)).encode("utf-8")


@dataclass
class World:
    settings: Settings  # real services (index, storage, database)
    embed_settings: Settings  # same, with service names renamed so the loopback address is not on the SSRF deny list
    owner: Account
    dataset: kb.DatasetRecord
    fake: FakeProvider
    api_key: str = ""

    @property
    def index(self) -> str:
        return index_name(self.owner.tenant_id)

    def store(self):
        return get_doc_store(self.settings)

    def deps(self, settings: Settings | None = None, ingest: dict[str, Any] | None = None) -> PipelineDeps:
        cfg = settings or self.settings
        if ingest:
            cfg = dataclasses.replace(cfg, ingest=dataclasses.replace(cfg.ingest, **ingest))
        limiters = Limiters.from_settings(cfg.ingest)
        embed_cfg = dataclasses.replace(self.embed_settings, ingest=cfg.ingest)
        return PipelineDeps(cfg, get_storage(cfg), get_doc_store(cfg), EmbedRunner(embed_cfg, limiters), limiters)


def world_settings(llm_key: bytes | None = None) -> tuple[Settings, Settings]:
    base = load_settings()
    llm = dataclasses.replace(
        base.llm,
        encryption_key=urlsafe_b64encode(llm_key or os.urandom(32)).decode(),
        key_id="k1",
        allow_private_base_urls=True,
        chat_timeout_seconds=10,
        embedding_timeout_seconds=2,
        max_retries=1,
    )
    real = dataclasses.replace(base, llm=llm)
    renamed = dataclasses.replace(
        real,
        mysql=dataclasses.replace(base.mysql, host="mysql"),
        redis=dataclasses.replace(base.redis, host="redis"),
        minio=dataclasses.replace(base.minio, host="minio"),
        es=dataclasses.replace(base.es, hosts="http://es01:9200"),
    )
    return real, renamed


def make_pipeline_world(registry: AccountRegistry, fake: FakeProvider, *, embedding_model: str = "fake-embed") -> World:
    real, renamed = world_settings()
    fake.embedding_dim = DIMENSION
    owner = registry.register(prefix="pipe")
    api_key = "-".join(("sk", "fake", uuid.uuid4().hex[:24]))
    structure.save_instance(
        real.llm, owner.tenant_id, COMPAT, "default", api_key=api_key, api_base=fake.base_url, api_version=None,
        models=list(EMBED_MODELS), replace_key=True,
    )
    structure.set_defaults(owner.tenant_id, embedding=ModelRef(embedding_model, "default", COMPAT))
    scope = ActingScope(tenant_id=owner.tenant_id, role="owner", subject="owner")
    dataset = kb.create_dataset(real, scope, owner.user_id, kb.CreateRequest(name=f"pipe-{uuid.uuid4().hex[:8]}"))
    return World(real, renamed, owner, dataset, fake, api_key)


def add_document(world: World, name: str, data: bytes, parser_config: dict[str, Any] | None = None) -> str:
    visible = docs.authorize_upload(principal_of(world.owner), world.dataset.id)
    made = docs.upload_documents(world.settings, visible, world.owner.user_id, [UploadItem(name=name, mime="application/octet-stream", stream=io.BytesIO(data))])
    doc_id = made[0]["id"]
    if parser_config:
        import json

        sql("UPDATE `document` SET `parser_config` = %s WHERE `id` = %s", (json.dumps(parser_config), doc_id))
    return doc_id


def add_task(doc_id: str, from_page: int = 0, to_page: int = 1000000) -> str:
    """One task row for the range, with the document marked running (what start_parse leaves behind)."""
    task_id = uuid.uuid4().hex
    with DB.connection_context():
        Task.create(id=task_id, doc_id=doc_id, from_page=from_page, to_page=to_page, task_type="parse", priority=0, digest="t", progress=0)
    sql("UPDATE `document` SET `run` = '1' WHERE `id` = %s", (doc_id,))
    return task_id


def run_task(world: World, task_id: str, control: TaskControl | None = None, deps: PipelineDeps | None = None) -> PipelineResult:
    from api.db.services.task_service import load_task_context

    ctx = load_task_context(task_id)
    assert ctx is not None
    return run_pipeline(ctx, control or TaskControl(), deps or world.deps())


def indexed(world: World, **condition: Any) -> list[dict]:
    """Every chunk matching ``condition`` (for example ``doc_id=[...]`` or ``task_id=[...]``), fields included."""
    result = search(world.store(), world.index, [world.dataset.id], condition=dict(condition), limit=2000)
    return list(result.hits)


def progress_msg(task_id: str) -> str:
    return str(sql("SELECT `progress_msg` FROM `task` WHERE `id` = %s", (task_id,))[0][0] or "")


def cleanup_tasks(registry: AccountRegistry) -> None:
    for acc in registry.created:
        sql("DELETE FROM `task` WHERE `doc_id` IN (SELECT `id` FROM `document` WHERE `kb_id` IN (SELECT `id` FROM `knowledgebase` WHERE `tenant_id` = %s))", (acc.tenant_id,))


# ----------------------------------------------------------------------------- roll-up and executor helpers (plan 04-12)


def put_chunks(world: World, doc_id: str, count: int, *, task_id: str = "", tokens: int = 10, enabled: bool = True) -> list[str]:
    """Insert ``count`` chunk rows straight into the index (no pipeline), with the fields the roll-up reads."""
    from common.doc_store.doc_store_base import vector_field

    store = world.store()
    store.create_idx(world.index, world.dataset.id, DIMENSION, "naive")
    rows = []
    for i in range(count):
        vector = [1.0] + [0.0] * (DIMENSION - 1)
        rows.append(
            {
                "id": f"{doc_id}_{i}", "doc_id": doc_id, "content_ltks": f"chunk {i}", "title_tks": "title", "position_int": [[1, 0, 0, 1, 1]],
                "available_int": 1, vector_field(DIMENSION): vector, "task_id": task_id, "token_num_int": tokens, "origin_kwd": "parsed",
                "doc_enabled_int": 1 if enabled else 0, "order_int": i,
            }
        )
    assert store.insert(rows, world.index, world.dataset.id) == []
    return [r["id"] for r in rows]


def set_task(task_id: str, progress: float, msg: str = "", retry_count: int = 0) -> None:
    sql("UPDATE `task` SET `progress` = %s, `progress_msg` = %s, `retry_count` = %s WHERE `id` = %s", (progress, msg, retry_count, task_id))


def age_task(task_id: str, seconds: int) -> None:
    """Make the task row look untouched for ``seconds`` (the reconciler reads ``update_time``)."""
    sql("UPDATE `task` SET `update_time` = %s WHERE `id` = %s", (int(time.time() * 1000) - seconds * 1000, task_id))


def begin_run(doc_id: str, tasks: int = 1) -> str:
    """The open log row and the begin time a real ``start_parse`` leaves behind. Returns the log row id."""
    from api.db.models import PipelineOperationLog
    from api.db.models.base import current_timestamp_ms

    began = datetime.datetime.now() - datetime.timedelta(seconds=3)
    sql("UPDATE `document` SET `process_begin_at` = %s WHERE `id` = %s", (began, doc_id))
    owner = sql("SELECT `kb_id`, `parser_id`, `name`, `suffix`, `type` FROM `document` WHERE `id` = %s", (doc_id,))[0]
    tenant = sql("SELECT `tenant_id` FROM `knowledgebase` WHERE `id` = %s", (owner[0],))[0][0]
    log_id = uuid.uuid4().hex
    with DB.connection_context():
        PipelineOperationLog.create(
            id=log_id, document_id=doc_id, tenant_id=tenant, kb_id=owner[0], parser_id=owner[1], document_name=owner[2], document_suffix=owner[3],
            document_type=owner[4], source_from="local", progress=0.0, process_begin_at=began, dsl={"tasks": tasks}, task_type="parse",
            operation_status="running", update_time=current_timestamp_ms(),
        )
    return log_id


def doc_state(doc_id: str) -> dict[str, Any]:
    run, progress, msg, chunks, duration = sql("SELECT `run`, `progress`, `progress_msg`, `chunk_num`, `process_duration` FROM `document` WHERE `id` = %s", (doc_id,))[0]
    return {"run": run, "progress": float(progress), "progress_msg": msg or "", "chunk_num": int(chunks), "process_duration": float(duration or 0)}


def log_state(doc_id: str) -> dict[str, Any]:
    import json

    status, progress, msg, dsl = sql(
        "SELECT `operation_status`, `progress`, `progress_msg`, `dsl` FROM `pipeline_operation_log` WHERE `document_id` = %s ORDER BY `create_time` DESC LIMIT 1", (doc_id,)
    )[0]
    parsed = json.loads(dsl) if isinstance(dsl, (str, bytes)) else dict(dsl or {})
    return {"status": status, "progress": float(progress or 0), "progress_msg": msg or "", "dsl": parsed}


def task_state(task_id: str) -> dict[str, Any]:
    progress, retry, msg = sql("SELECT `progress`, `retry_count`, `progress_msg` FROM `task` WHERE `id` = %s", (task_id,))[0]
    return {"progress": float(progress), "retry_count": int(retry), "progress_msg": msg or ""}


# ----------------------------------------------------------------------------- stack-side helpers (plan 04-14)
# These drive the running stack through Nginx (upload, parse, list) and read the index and the task table from the host.
# The ``api`` argument is the ``api(ingress, method, path, token, body=..., params=...)`` callable of test_provider_flow.

_DATASETS = "/api/v1/datasets"


def upload_text(
    ingress: Any, who: Any, dataset_id: str, data: bytes, name: str | None = None, *, params: dict[str, str] | None = None, mime: str = "text/plain"
) -> dict[str, Any]:
    """Upload one text file through the real route and return its document view."""
    ingress.cookies.clear()
    file_name = name or f"doc-{uuid.uuid4().hex[:8]}.txt"
    resp = ingress.post(
        "/api/v1/documents/upload",
        headers={"Authorization": f"Bearer {who.token}"},
        params={"dataset_id": dataset_id, **(params or {})},
        files=[("file", (file_name, data, mime))],
        timeout=60.0,
    )
    assert resp.status_code == 200 and resp.json()["code"] == 0, resp.text
    return resp.json()["data"][0]


def start_parse(ingress: Any, who: Any, dataset_id: str, doc_ids: Any, run: str = "1", confirm: bool = False) -> Any:
    """The raw parse (or, with ``run="2"``, cancel) response."""
    ingress.cookies.clear()
    body: dict[str, Any] = {"doc_ids": doc_ids, "run": run}
    if confirm:
        body["confirm_replace"] = True
    return ingress.post(f"{_DATASETS}/{dataset_id}/documents/parse", headers={"Authorization": f"Bearer {who.token}"}, json=body, timeout=60.0)


def doc_row(ingress: Any, who: Any, dataset_id: str, doc_id: str) -> dict[str, Any]:
    ingress.cookies.clear()
    resp = ingress.get(f"{_DATASETS}/{dataset_id}/documents", headers={"Authorization": f"Bearer {who.token}"}, params={"page_size": "100"}, timeout=30.0)
    assert resp.status_code == 200, resp.text
    for item in resp.json()["data"]["items"]:
        if item["id"] == doc_id:
            return item
    raise AssertionError(f"document {doc_id} not listed")


def dataset_row(ingress: Any, who: Any, dataset_id: str) -> dict[str, Any]:
    ingress.cookies.clear()
    resp = ingress.get(f"{_DATASETS}/{dataset_id}", headers={"Authorization": f"Bearer {who.token}"}, timeout=30.0)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def index_count(settings: Settings, tenant_id: str, dataset_id: str, doc_id: str) -> int:
    """Chunks of one document in Elasticsearch, read from the host."""
    return int(get_doc_store(settings).stats({"doc_id": [doc_id]}, index_name(tenant_id), dataset_id).count)


def task_rows(doc_id: str) -> list[str]:
    """Ids of the task rows of a document (host-side MySQL read)."""
    return [str(r[0]) for r in sql("SELECT `id` FROM `task` WHERE `doc_id` = %s", (doc_id,))]


def wait_run(ingress: Any, who: Any, dataset_id: str, doc_id: str, run: str, timeout: float = 120.0) -> dict[str, Any]:
    """Poll the document list until ``run`` is reached; returns the row."""
    from test.helpers.wait import wait_until

    return wait_until(
        lambda: (lambda row: row if row["run"] == run else None)(doc_row(ingress, who, dataset_id, doc_id)),
        timeout=timeout,
        interval=1.0,
        describe=lambda: f"document {doc_id} never reached run {run}",
    )
