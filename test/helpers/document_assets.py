"""Seed an actual owned PNG through the production persistence service for route matrices."""

from pathlib import Path


def owned_image(world) -> str:
    if world.a_image_id:
        return world.a_image_id
    from api.db.database import init_database
    from api.db.services.document_asset_service import persist_assets
    from api.db.services.task_service import load_task_context
    from common.settings import load_settings
    from rag.parsers.assets import ParsedAsset
    from rag.svr.control import TaskControl
    from test.helpers.ingest import add_task, begin_run
    from test.helpers.uploads import sql
    from test.testcases._matrix_fixtures import _ok, bearer

    settings = load_settings()
    init_database(settings.mysql)
    response = world.client.post(
        "/api/v1/documents/upload",
        headers=bearer(world.a.token),
        params={"dataset_id": world.a_team_dataset["id"]},
        files={"file": ("matrix-image-source.txt", b"IMAGEARCHIVEFACT 9100", "text/plain")},
    )
    doc = _ok(response, "asset original source")["data"][0]["id"]
    task = add_task(doc)
    generation = begin_run(doc)
    raw = (Path(__file__).resolve().parents[1] / "fixtures/phase6/ocr-planted.png").read_bytes()
    image = ParsedAsset.from_png(raw, width=1400, height=400, caption="IMAGEARCHIVEFACT 9100")
    identifier = persist_assets(settings, load_task_context(task), generation, [image], TaskControl())[0]
    sql("UPDATE `task` SET `progress`=1 WHERE `id`=%s", (task,))
    sql("UPDATE `document` SET `run`='3' WHERE `id`=%s", (doc,))
    sql("UPDATE `pipeline_operation_log` SET `operation_status`='done' WHERE `id`=%s", (generation,))
    world.a_image_id = identifier
    return identifier
