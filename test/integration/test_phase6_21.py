"""Real MySQL, Elasticsearch and local test-provider enrichment."""
import json
import pytest
from api.db.services import tenant_model_service as models
from common.model_ref import ModelRef
from common.doc_store.doc_store_base import MatchTextExpr
from rag.svr.failure import TaskFailure
from rag.nlp.search import RetrievalRequest, Retriever
from test.integration import test_pipeline_failures as base
from test.helpers.ingest import add_document, add_task, indexed, run_task
from test.helpers.doc_store_contract import search
from test.helpers.uploads import sql

_bound_database = base._bound_database
registry = base.registry
fake = base.fake
world = base.world
pytestmark = pytest.mark.integration


def _model(world):
    models.add_models(world.settings.llm, world.owner.tenant_id, "OpenAI-API-Compatible", "default",
                      [models.NewModel("fake-enrichment", "chat", None, 8192)])
    models.set_defaults(world.owner.tenant_id, chat=ModelRef("fake-enrichment", "default", "OpenAI-API-Compatible"))


def _text(repo_root):
    return " ".join((repo_root / "test/fixtures/phase6/enrichment-original.txt").read_text().split())


def test_off_has_zero_calls_and_enabled_terms_are_indexed_without_source_rewrite(world, fake, repo_root):
    source = _text(repo_root)
    _model(world)
    before = len(fake.chat_requests())
    off = add_document(world, "off.txt", source.encode())
    run_task(world, add_task(off))
    assert len(fake.chat_requests()) == before
    fake.chat_response = json.dumps({"items":[{"index":0,"keywords":["beacon altitude"],
                                               "questions":["How high is the east lighthouse?"]}]})
    doc = add_document(world, "enriched.txt", source.encode(), {"auto_keywords": 2, "auto_questions": 1})
    run_task(world, add_task(doc))
    rows = indexed(world, doc_id=[doc])
    assert len(rows) == 1 and len(fake.chat_requests()) == before + 1
    row = rows[0]
    assert row["content_with_weight"] == source
    assert row["important_kwd"] == ["beacon altitude"]
    assert "beacon" in row["important_tks"]
    assert "lighthouse" in row["question_tks"]
    assert row["generated_questions_kwd"] == ["How high is the east lighthouse?"]
    assert row["position_int"] == []
    matched = search(world.store(), world.index, [world.dataset.id], condition={"doc_id":[doc]},
                     matches=[MatchTextExpr(["important_tks"], "beacon", 10)])
    assert len(matched.hits) == 1 and matched.hits[0]["id"] == row["id"]
    product = Retriever(world.store(), world.settings).retrieve(RetrievalRequest(
        tenant_id=world.owner.tenant_id, dataset_ids=[world.dataset.id], doc_ids=[doc],
        question="beacon altitude", query_vector=row["q_8_vec"], vector_dim=8,
        vector_similarity_weight=0.0, similarity_threshold=0.5,
    ))
    assert [hit.chunk_id for hit in product.hits] == [row["id"]]
    assert product.hits[0].term_similarity == 1.0
    # An explicit text edit invalidates hints about the old content.
    from api.db.services.chunk_service import update_chunk
    from api.db.services.document_service import authorize_upload
    from test.integration.test_knowledgebase_service import principal_of
    principal = principal_of(world.owner)
    sql("UPDATE `document` SET `run`='3' WHERE `id`=%s", (doc,))
    update_chunk(world.embed_settings, authorize_upload(principal, world.dataset.id), principal, doc, row["id"], text="Corrected lighthouse source.", doc_store=world.store())
    edited = indexed(world, doc_id=[doc])[0]
    assert edited["content_with_weight"] == "Corrected lighthouse source."
    assert not edited.get("important_kwd") and not edited.get("generated_questions_kwd")
    assert not edited.get("question_tks")


def test_bad_response_refuses_once_before_index_publication(world, fake, repo_root):
    _model(world)
    fake.chat_response = "not json"
    doc = add_document(world, "bad-enrichment.txt", _text(repo_root).encode(), {"auto_keywords": 1})
    before = len(fake.chat_requests())
    with pytest.raises(TaskFailure) as err:
        run_task(world, add_task(doc))
    assert err.value.code == "provider_refused"
    assert not indexed(world, doc_id=[doc])
    assert len(fake.chat_requests()) == before + 1


def test_enabled_without_chat_default_refuses_before_provider_or_index(world, fake, repo_root):
    doc = add_document(world, "no-chat.txt", _text(repo_root).encode(), {"auto_keywords": 1})
    before = len(fake.chat_requests())
    with pytest.raises(TaskFailure) as err:
        run_task(world, add_task(doc))
    assert err.value.code == "model_unavailable"
    assert len(fake.chat_requests()) == before and not indexed(world, doc_id=[doc])
