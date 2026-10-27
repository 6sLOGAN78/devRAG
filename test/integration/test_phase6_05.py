"""Actual bounded native normalization and asset ownership on the real database/storage."""

import base64
import hashlib

import httpx
import pytest

from test.conftest import stack_env

pytestmark = pytest.mark.integration


def test_actual_native_image_normalization_is_deterministic(repo_root):
    token = stack_env().get("DEEPDOC_API_TOKEN")
    assert token, "real native service is required"
    original = (repo_root / "test/fixtures/phase6/ocr-planted.png").read_bytes()
    with httpx.Client(base_url="http://127.0.0.1:9390", timeout=65) as client:
        results = []
        for _ in range(2):
            response = client.post("/v1/images/normalize", headers={"Authorization": f"Bearer {token}"}, files={"file": ("image.png", original)})
            assert response.status_code == 200, response.text
            data = response.json()["image"]
            raw = base64.b64decode(data["content_base64"], validate=True)
            assert raw.startswith(b"\x89PNG\r\n\x1a\n") and data["sha256"] == hashlib.sha256(raw).hexdigest()
            assert data["width"] == 1400 and data["height"] == 400
            results.append(raw)
    assert results[0] == results[1]


@pytest.mark.parametrize("suffix", ["docx", "pptx"])
def test_actual_office_images_normalize_remotely_without_host_image_decode(repo_root, monkeypatch, suffix):
    import importlib
    from types import SimpleNamespace

    from PIL import Image

    from common.settings import DeepDocSettings
    from rag.parsers.types import ParseReport, SourceFile

    def no_decode(*args, **kwargs):
        raise AssertionError("native image decode crossed worker boundary")

    monkeypatch.setattr(Image, "open", no_decode)
    token = stack_env().get("DEEPDOC_API_TOKEN")
    assert token
    settings = SimpleNamespace(deepdoc=DeepDocSettings(url="http://127.0.0.1:9390", api_token=token))
    path = repo_root / f"test/fixtures/phase6/figures-duplicate.{suffix}"
    report = ParseReport()
    blocks = list(importlib.import_module("rag.parsers." + suffix).parse(SourceFile(path, suffix, path.stat().st_size), report, settings=settings))
    assets = [asset for block in blocks for asset in block.assets]
    assert len(assets) == 2 and len({asset.sha256 for asset in assets}) == 1 and report.images_skipped == 0
    assert all(asset.width == 1400 and asset.height == 400 for asset in assets)


def test_real_owned_asset_dedup_generation_gc_and_authorize_before_storage(repo_root):
    import importlib.util

    assert importlib.util.find_spec("api.db.services.document_asset_service"), "owned asset persistence/download service is missing"
    from api.db.database import DB, init_database
    from api.db.models import DocumentAsset, Task
    from api.db.services import document_asset_service as assets
    from api.db.services import document_service as docs
    from api.db.services.service_errors import Kind, ServiceError
    from api.db.services.task_service import load_task_context
    from common.constants import BUCKET_NAME
    from common.settings import load_settings
    from rag.parsers.assets import ParsedAsset
    from rag.svr.control import LockLost, TaskCancelled, TaskControl
    from rag.utils.storage_base import StorageError
    from rag.utils.storage_factory import get_storage
    from test.helpers.accounts import AccountRegistry
    from test.helpers.fake_provider import running_stack_fake_provider
    from test.helpers.ingest import add_document, add_task, begin_run, make_pipeline_world
    from test.helpers.uploads import sql
    from test.integration.test_knowledgebase_service import principal_of
    from test.testcases.conftest import BASE_URL

    init_database(load_settings().mysql)
    registry = AccountRegistry(BASE_URL)
    try:
        with running_stack_fake_provider() as fake:
            world = make_pipeline_world(registry, fake)
            foreign = registry.register(prefix="asset-foreign")
            image = ParsedAsset.from_png((repo_root / "test/fixtures/phase6/ocr-planted.png").read_bytes(), width=1400, height=400, caption="<img src=x onerror=alert(1)>")
            owned = []
            for name in ("first.txt", "second.txt"):
                doc = add_document(world, name, b"IMAGEARCHIVEFACT 9100")
                task = add_task(doc)
                generation = begin_run(doc)
                ctx = load_task_context(task)
                ids = assets.persist_assets(world.settings, ctx, generation, [image, image], TaskControl())
                assert len(ids) == 1
                with DB.connection_context():
                    assert DocumentAsset.select().where(DocumentAsset.doc_id == doc).count() == 1
                sql("UPDATE `document` SET `run`='3' WHERE `id`=%s", (doc,))
                sql("UPDATE `pipeline_operation_log` SET `operation_status`='done' WHERE `id`=%s", (generation,))
                assert assets.read_asset(world.settings, principal_of(world.owner), ids[0]) == image.content
                owned.append((doc, task, generation, ids[0]))
            assert owned[0][3] != owned[1][3]
            with DB.connection_context():
                first_key = DocumentAsset.get_by_id(owned[0][3]).object_key
                second_key = DocumentAsset.get_by_id(owned[1][3]).object_key
            storage = get_storage(world.settings)
            assert storage.exists(BUCKET_NAME, first_key) and storage.exists(BUCKET_NAME, second_key)

            class NoStorage:
                def get(self, *args):
                    raise AssertionError("unauthorized object read")

            for principal, image_id in ((principal_of(foreign), owned[0][3]), (principal_of(world.owner), "0" * 32)):
                with pytest.raises(ServiceError) as error:
                    assets.read_asset(world.settings, principal, image_id, storage=NoStorage())
                assert error.value.kind == Kind.NOT_FOUND
            first, task, old, identifier = owned[0]
            replaced_ctx = load_task_context(task)
            sql("UPDATE `document` SET `run`='1' WHERE `id`=%s", (first,))
            with DB.connection_context():
                Task.delete().where(Task.id == task).execute()
            add_task(first)
            new = begin_run(first)
            with pytest.raises(TaskCancelled):
                assets.persist_assets(world.settings, replaced_ctx, old, [image], TaskControl())
            with pytest.raises(ServiceError):
                assets.read_asset(world.settings, principal_of(world.owner), identifier, storage=NoStorage())
            sql("UPDATE `document` SET `run`='3' WHERE `id`=%s", (first,))
            sql("UPDATE `pipeline_operation_log` SET `operation_status`='done' WHERE `id`=%s", (new,))
            assets.prune_obsolete(world.settings, world.dataset.id, first)
            assert not storage.exists(BUCKET_NAME, first_key)
            assert storage.exists(BUCKET_NAME, second_key)
            with DB.connection_context():
                assert not DocumentAsset.select().where(DocumentAsset.doc_id == first).exists()
            assert assets.read_asset(world.settings, principal_of(world.owner), owned[1][3]) == image.content
            # A lost worker must retain its control signal even when compensation fails.
            cancelled_doc = add_document(world, "lost-owner.txt", b"owned cancellation fact")
            cancelled_task = add_task(cancelled_doc)
            cancelled_generation = begin_run(cancelled_doc)
            control = TaskControl()

            class LostDuringPut:
                def put(self, bucket, key, content):
                    storage.put(bucket, key, content)
                    self.key = key
                    control.lost.set()

                def rm(self, *args):
                    raise StorageError("cleanup unavailable")

            interrupted_storage = LostDuringPut()
            with pytest.raises(LockLost):
                assets.persist_assets(world.settings, load_task_context(cancelled_task), cancelled_generation, [image], control, storage=interrupted_storage)
            with DB.connection_context():
                assert not DocumentAsset.select().where(DocumentAsset.doc_id == cancelled_doc).exists()
            storage.rm(BUCKET_NAME, interrupted_storage.key)
            visible = docs.authorize_upload(principal_of(world.owner), world.dataset.id)
            docs.delete_documents(world.settings, visible, world.owner.user_id, [owned[1][0]])
            assert not storage.exists(BUCKET_NAME, second_key)
            with pytest.raises(ServiceError):
                assets.read_asset(world.settings, principal_of(world.owner), owned[1][3], storage=NoStorage())
            with DB.connection_context():
                assert not DocumentAsset.select().where(DocumentAsset.doc_id == owned[1][0]).exists()
    finally:
        with DB.connection_context():
            if registry.created:
                DocumentAsset.delete().where(DocumentAsset.tenant_id.in_([a.tenant_id for a in registry.created])).execute()
        registry.cleanup()


def test_actual_pdf_embedded_image_bytes_and_geometry(repo_root):
    token = stack_env().get("DEEPDOC_API_TOKEN")
    assert token
    with httpx.Client(base_url="http://127.0.0.1:9390", timeout=65) as client:
        result = client.post(
            "/v1/parse",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("figures.pdf", (repo_root / "test/fixtures/phase6/figures-mixed.pdf").read_bytes())},
            data={"options": '{"layout":false}'},
        )
    assert result.status_code == 200, result.text
    blocks = [block for block in result.json()["blocks"] if block.get("assets")]
    assert blocks, "PDF embedded images do not reach the typed native response"
    assert blocks[0]["assets"][0]["page"] == 2
    assert blocks[0]["boxes"][0] == {"page": 2, "x0": 0.0, "top": 0.0, "x1": 700.0, "bottom": 200.0}
    raw = base64.b64decode(blocks[0]["assets"][0]["content_base64"], validate=True)
    assert raw.startswith(b"\x89PNG\r\n\x1a\n")
    assert hashlib.sha256(raw).hexdigest() == blocks[0]["assets"][0]["sha256"]


def test_native_vector_region_crop_preserves_actual_pixels_and_page_box():
    import subprocess

    code = """from PIL import Image
from deepdoc.geometry import Region
from deepdoc.pdf_service import _region_assets
from rag.parsers.assets import decode_asset, encode_asset
from io import BytesIO
image = Image.new("RGB", (600, 400), "white")
image.paste((12, 34, 56), (60, 80, 240, 200))
blocks = _region_assets(image, [Region(5, 0.9, (30, 40, 120, 100))], [], 7, 300, 200)
assert len(blocks) == 1
b = blocks[0]
assert b.boxes[0].page == 7 and b.boxes[0].x0 == 30 and b.boxes[0].bottom == 100
asset = decode_asset(encode_asset(b.assets[0]))
assert asset.kind == "table" and asset.page == 7 and (asset.width, asset.height) == (180, 120)
assert Image.open(BytesIO(asset.content)).getpixel((20, 20)) == (12, 34, 56)
"""
    result = subprocess.run(["docker", "exec", "-i", "devrag-stack-deepdoc-1", "/ragflow/.venv/bin/python", "-"], input=code, text=True, capture_output=True, check=False, timeout=30)
    assert result.returncode == 0, result.stderr
