"""Vision capability union and sealed credentials against the actual database."""

import pytest
from test.integration import test_tenant_model_service as base
from api.db.services import tenant_model_service as models, tenant_llm_service as credentials
from common.model_ref import ModelRef

_bound_database = base._bound_database
llm = base.llm
account = base.account
from test.integration.test_provider_service import limiter as provider_limiter

pytestmark = pytest.mark.integration


def test_chat_then_vision_preserve_identity_default_and_tenant_key(llm, account):
    provider = "OpenAI-API-Compatible"
    name = "shared-vision-test"
    key = base.fake_key()
    first = models.save_instance(
        llm, account.tenant_id, provider, "default", api_key=key, api_base="https://example.invalid/v1", api_version=None, models=[models.NewModel(name, "chat", None, 8192)], replace_key=True
    )
    original = first.models[0]
    ref = ModelRef(name, "default", provider)
    models.set_defaults(account.tenant_id, chat=ref)
    try:
        saved = models.add_models(llm, account.tenant_id, provider, "default", [models.NewModel(name, "vision", None, 8192)])
    except Exception as exc:
        pytest.fail(f"Distinct vision capability was refused: {type(exc).__name__}")
    selected = [m for m in saved.models if m.model == name]
    assert {m.model_type for m in selected} == {"chat", "vision"}
    assert {m.id for m in selected} == {original.id}
    assert {m.composite for m in selected} == {original.composite}
    assert models.get_defaults(account.tenant_id).chat == original.composite
    for kind in ["chat", "vision"]:
        found = credentials.get_credential(llm, account.tenant_id, ref, kind)
        assert found is not None and found.api_key == key
        assert credentials.get_credential(llm, "0" * 32, ref, kind) is None
    from api.db.database import DB
    from api.db.models import TenantModel

    with DB.connection_context():
        assert TenantModel.get_by_id(original.id).model_type == 9


from test.integration import test_pipeline_failures as pipeline_base

registry = pipeline_base.registry
fake = pipeline_base.fake
world = pipeline_base.world


def test_real_picture_normalization_caption_index_and_owned_image(world, fake, repo_root):
    from dataclasses import replace
    from common.settings import DeepDocSettings
    from test.conftest import stack_env
    from test.helpers.ingest import add_document, add_task, begin_run, run_task, indexed
    from test.helpers.uploads import sql
    from api.db.database import DB
    from api.db.models import DocumentAsset

    ref = "fake-vision@OpenAI-API-Compatible"
    models.add_models(world.settings.llm, world.owner.tenant_id, "OpenAI-API-Compatible", "default", [models.NewModel("fake-vision", "vision", None, 8192)])
    p = repo_root / "test/fixtures/phase6/picture-original.png"
    doc = add_document(world, p.name, p.read_bytes(), parser_config={"image_model": ref})
    sql("UPDATE `document` SET `parser_id`=%s WHERE `id`=%s", ("picture", doc))
    task = add_task(doc)
    begin_run(doc)
    token = stack_env().get("DEEPDOC_API_TOKEN")
    assert token
    settings = replace(world.settings, deepdoc=DeepDocSettings(url="http://127.0.0.1:9390", api_token=token))
    result = run_task(world, task, deps=world.deps(settings=settings))
    assert result.chunk_count == 1
    rows = indexed(world, doc_id=[doc])
    assert len(rows) == 1
    assert "52 metres" in rows[0]["content_with_weight"] and "73 units" in rows[0]["content_with_weight"]
    assert rows[0]["position_int"] == []
    with DB.connection_context():
        assets = list(DocumentAsset.select().where(DocumentAsset.doc_id == doc))
        assert len(assets) == 1 and assets[0].id in rows[0]["image_ids_kwd"]
    sent = [r for r in fake.requests if r.path.endswith("/chat/completions")]
    assert len(sent) == 1
    assert sent[0].body["messages"][-1]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_inactive_vision_structure_cannot_open_sealed_key(llm, account):
    from api.db.database import DB
    from api.db.models import TenantModel

    provider = "OpenAI-API-Compatible"
    ref = ModelRef("inactive-vision", "default", provider)
    saved = models.save_instance(
        llm,
        account.tenant_id,
        provider,
        "default",
        api_key=base.fake_key(),
        api_base="https://example.invalid/v1",
        api_version=None,
        models=[models.NewModel(ref.model, "vision", None, 8192)],
        replace_key=True,
    )
    with DB.connection_context():
        TenantModel.update(status="inactive").where(TenantModel.id == saved.models[0].id).execute()
    assert credentials.get_credential(llm, account.tenant_id, ref, "vision") is None
    assert models.list_models(account.tenant_id, "vision") == []


def test_provider_probe_accepts_same_name_chat_vision_with_real_multimodal_call(account, fake, provider_limiter):
    from test.integration.test_provider_service import make_settings
    from api.db.services.provider_service import save_provider, SaveRequest, ModelRequest

    settings = make_settings()
    saved = save_provider(
        settings,
        SaveRequest(
            tenant_id=account.tenant_id,
            provider="OpenAI-API-Compatible",
            api_key=base.fake_key(),
            base_url=fake.base_url,
            models=(ModelRequest("shared-multimodal", "chat"), ModelRequest("shared-multimodal", "vision")),
        ),
        limiter=provider_limiter,
    )
    assert {m.model_type for m in saved.models} == {"chat", "vision"}
    assert len({m.id for m in saved.models}) == 1
    requests = [r for r in fake.requests if r.path.endswith("/chat/completions")]
    assert len(requests) == 2
    assert isinstance(requests[1].body["messages"][-1]["content"], list)


def test_real_ocr_only_picture_uses_native_text_and_no_vision_request(world, fake, repo_root):
    from dataclasses import replace
    from common.settings import DeepDocSettings
    from test.conftest import stack_env
    from test.helpers.ingest import add_document, add_task, begin_run, run_task, indexed
    from test.helpers.uploads import sql

    p = repo_root / "test/fixtures/phase6/ocr-planted.png"
    doc = add_document(world, p.name, p.read_bytes(), parser_config={"picture_ocr_only": True})
    sql("UPDATE `document` SET `parser_id`=%s WHERE `id`=%s", ("picture", doc))
    task = add_task(doc)
    begin_run(doc)
    settings = replace(world.settings, deepdoc=DeepDocSettings(url="http://127.0.0.1:9390", api_token=stack_env()["DEEPDOC_API_TOKEN"]))
    result = run_task(world, task, deps=world.deps(settings=settings))
    rows = indexed(world, doc_id=[doc])
    assert result.chunk_count == 1
    text = rows[0]["content_with_weight"].upper()
    assert "LIGHTHOUSE" in text and "52" in text and "ORCHARD" in text and "9100" in text
    assert rows[0]["position_int"] and rows[0]["image_ids_kwd"]
    assert not any(r.path.endswith("/chat/completions") for r in fake.requests)


def test_picture_without_model_refuses_before_provider_or_asset_publication(world, fake, repo_root):
    from dataclasses import replace
    from common.settings import DeepDocSettings
    from test.conftest import stack_env
    from test.helpers.ingest import add_document, add_task, begin_run, run_task, indexed
    from test.helpers.uploads import sql
    from rag.svr.failure import TaskFailure

    p = repo_root / "test/fixtures/phase6/picture-original.png"
    doc = add_document(world, p.name, p.read_bytes())
    sql("UPDATE `document` SET `parser_id`=%s WHERE `id`=%s", ("picture", doc))
    task = add_task(doc)
    begin_run(doc)
    settings = replace(world.settings, deepdoc=DeepDocSettings(url="http://127.0.0.1:9390", api_token=stack_env()["DEEPDOC_API_TOKEN"]))
    with pytest.raises(TaskFailure) as error:
        run_task(world, task, deps=world.deps(settings=settings))
    assert error.value.code == "model_unavailable"
    assert indexed(world, doc_id=[doc]) == []
    assert not any(r.path.endswith("/chat/completions") for r in fake.requests)


def test_inactive_provider_instance_is_not_offered_as_a_default_instance(llm, account):
    from api.db.database import DB
    from api.db.models import TenantModelInstance, TenantModel

    provider = "OpenAI-API-Compatible"
    name = "inactive-instance-vision"
    saved = models.save_instance(
        llm,
        account.tenant_id,
        provider,
        "photos",
        api_key=base.fake_key(),
        api_base="https://example.invalid/v1",
        api_version=None,
        models=[models.NewModel(name, "vision", None, 8192)],
        replace_key=True,
    )
    with DB.connection_context():
        instance_id = TenantModel.get_by_id(saved.models[0].id).instance_id
        TenantModelInstance.update(status="inactive").where(TenantModelInstance.id == instance_id).execute()
    assert credentials.get_credential(llm, account.tenant_id, ModelRef(name, "photos", provider), "vision") is None
    assert models.list_models(account.tenant_id, "vision") == []
