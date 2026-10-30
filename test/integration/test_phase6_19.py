"""Original tag/PageRank source producers and authorized dataset lifecycle on actual services."""
import pytest
from test.integration import test_pipeline_failures as base
from test.helpers.ingest import add_document,add_task,run_task,indexed
from test.helpers.uploads import sql

_bound_database=base._bound_database
registry=base.registry
fake=base.fake
world=base.world
pytestmark=pytest.mark.integration


def test_original_tag_worker_indexes_weights_and_authorized_dataset_pagerank(world,repo_root):
    path=repo_root/"test/fixtures/phase6/tags-original.txt"
    doc=add_document(world,path.name,path.read_bytes(),parser_config={"pagerank":99})
    sql("UPDATE `document` SET `parser_id`='tag' WHERE `id`=%s",(doc,))
    sql("UPDATE `knowledgebase` SET `pagerank`=2 WHERE `id`=%s",(world.dataset.id,))
    result=run_task(world,add_task(doc))
    rows=indexed(world,doc_id=[doc])
    assert result.chunk_count==len(rows)==1
    row=rows[0]
    assert row["tag_feas"]["lighthouse"]/row["tag_feas"]["calibration"]==pytest.approx(4/5)
    assert row.get("pagerank_fea")==2,"Actual dataset PageRank is absent or replaced by untrusted parser config"
    assert "52 metres" in row["content_with_weight"] and "73 units" in row["content_with_weight"]
    assert row["doc_id"]==doc and row["kb_id"]==world.dataset.id


def prepared(world,repo_root):
    path=repo_root/"test/fixtures/phase6/tags-original.txt"
    doc=add_document(world,path.name,path.read_bytes())
    sql("UPDATE `document` SET `parser_id`='tag' WHERE `id`=%s",(doc,))
    run_task(world,add_task(doc))
    sql("UPDATE `document` SET `run`='3' WHERE `id`=%s",(doc,))
    from test.integration.test_knowledgebase_service import principal_of
    return doc,principal_of(world.owner)


def test_tags_list_aggregate_delete_and_parse_fence_keep_other_source_data(world,repo_root):
    from api.db.services import dataset_tag_service as tags
    from api.db.services.service_errors import ServiceError
    doc,principal=prepared(world,repo_root)
    original=indexed(world,doc_id=[doc])[0]
    found=tags.list_tags(world.settings,principal,world.dataset.id)
    assert {item["tag"] for item in found["items"]}==set(original["tag_feas"])
    assert all(item["count"]==1 for item in found["items"])
    assert tags.aggregate_tags(world.settings,principal,[world.dataset.id])==found
    sql("UPDATE `document` SET `run`='1' WHERE `id`=%s",(doc,))
    with pytest.raises(ServiceError) as err:
        tags.delete_tags(world.settings,principal,world.dataset.id,["calibration"])
    assert err.value.reason=="parse_running"
    sql("UPDATE `document` SET `run`='3' WHERE `id`=%s",(doc,))
    deleted=tags.delete_tags(world.settings,principal,world.dataset.id,[" Calibration "])
    assert deleted=={"deleted":["calibration"],"count":1}
    after=indexed(world,doc_id=[doc])[0]
    assert "calibration" not in after["tag_feas"] and "lighthouse" in after["tag_feas"]
    assert after["content_with_weight"]==original["content_with_weight"] and after["q_8_vec"]==original["q_8_vec"]
    assert sum(value*value for value in after["tag_feas"].values())==pytest.approx(1)


def test_mixed_foreign_tag_selection_is_not_queried_or_partially_returned(world,repo_root):
    from api.db.services import dataset_tag_service as tags
    from api.db.services.service_errors import ServiceError
    _,principal=prepared(world,repo_root)
    class NoRead:
        def search(self,*args,**kwargs):
            pytest.fail("Index was queried before every dataset was authorized")
    with pytest.raises(ServiceError) as err:
        tags.aggregate_tags(world.settings,principal,[world.dataset.id,"f"*32],doc_store=NoRead())
    assert err.value.reason=="dataset_not_found"


def test_pagerank_setting_updates_current_rows_and_zero_clears_feature(world,repo_root):
    from api.db.services import knowledgebase_service as kb
    from api.db.services.service_errors import ServiceError
    doc,principal=prepared(world,repo_root)
    visible=kb.load_visible_dataset(principal,world.dataset.id)
    sql("UPDATE `document` SET `run`='1' WHERE `id`=%s",(doc,))
    with pytest.raises(ServiceError) as err:
        kb.update_dataset(world.settings,visible,world.owner.user_id,{"pagerank":3})
    assert err.value.reason=="parse_running"
    assert kb.load_visible_dataset(principal,world.dataset.id).dataset.pagerank==0
    sql("UPDATE `document` SET `run`='3' WHERE `id`=%s",(doc,))
    changed=kb.update_dataset(world.settings,visible,world.owner.user_id,{"pagerank":3})
    assert changed.pagerank==3 and indexed(world,doc_id=[doc])[0]["pagerank_fea"]==3
    visible=kb.load_visible_dataset(principal,world.dataset.id)
    changed=kb.update_dataset(world.settings,visible,world.owner.user_id,{"pagerank":0})
    assert changed.pagerank==0 and indexed(world,doc_id=[doc])[0]["pagerank_fea"] is None


def test_bounded_inventory_reads_real_rank_features(world,repo_root):
    import time
    from api.db.services import dataset_tag_service as tags
    from api.db.services import knowledgebase_service as kb
    _,principal=prepared(world,repo_root)
    rows=tags._inventory(world.store(),kb.load_visible_dataset(principal,world.dataset.id),10000,time.monotonic())
    assert rows and tags._summarize(rows)["total"]==6


def test_tag_manual_chunk_and_text_edit_keep_current_weights_and_dataset_rank(world,repo_root):
    from api.db.services import chunk_service,knowledgebase_service as kb
    doc,principal=prepared(world,repo_root)
    sql("UPDATE `knowledgebase` SET `pagerank`=2 WHERE `id`=%s",(world.dataset.id,))
    visible=kb.load_visible_dataset(principal,world.dataset.id)
    made=chunk_service.create_chunk(world.embed_settings,visible,principal,doc,"Lighthouse lighthouse calibration",doc_store=world.store())
    row=next(item for item in indexed(world,doc_id=[doc]) if item["id"]==made["id"])
    assert row["tag_feas"]["lighthouse"]>row["tag_feas"]["calibration"] and row["pagerank_fea"]==2
    chunk_service.update_chunk(world.embed_settings,visible,principal,doc,made["id"],text="Calibration calibration offset",doc_store=world.store())
    changed=next(item for item in indexed(world,doc_id=[doc]) if item["id"]==made["id"])
    assert "lighthouse" not in changed["tag_feas"]
    assert changed["tag_feas"]["calibration"]>changed["tag_feas"]["offset"]
    assert changed["content_with_weight"]=="Calibration calibration offset" and changed["pagerank_fea"]==2
