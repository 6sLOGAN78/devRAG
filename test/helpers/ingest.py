"""Shared builders for the ingestion pipeline tests (plan 04-11).

``paragraphs`` makes text whose chunk count is known from its arguments. ``make_pipeline_world`` creates a workspace whose embedding model points at
the loopback provider, a dataset, and helpers to upload a document, add task rows and run the pipeline against the real MySQL, MinIO and
Elasticsearch. The loopback provider is the other end of the wire, not a stub of devRag code.
"""

from __future__ import annotations

import dataclasses
import io
import os
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
    structure.save_instance(
        real.llm, owner.tenant_id, COMPAT, "default", api_key="-".join(("sk", "fake", uuid.uuid4().hex[:24])), api_base=fake.base_url, api_version=None,
        models=list(EMBED_MODELS), replace_key=True,
    )
    structure.set_defaults(owner.tenant_id, embedding=ModelRef(embedding_model, "default", COMPAT))
    scope = ActingScope(tenant_id=owner.tenant_id, role="owner", subject="owner")
    dataset = kb.create_dataset(real, scope, owner.user_id, kb.CreateRequest(name=f"pipe-{uuid.uuid4().hex[:8]}"))
    return World(real, renamed, owner, dataset, fake)


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
