"""Original weighted tag producer and exact retrieval-rank arithmetic contract."""
import math
import pytest
from rag.parsers.types import ParsedBlock

pytestmark = pytest.mark.unit


def tag_chunker():
    from rag.chunking.factory import available,get_chunker
    assert available("tag"), "Tag chunker is missing"
    return get_chunker("tag")


def test_original_tag_chunks_have_actual_normalized_weights_and_unchanged_source(repo_root):
    chunker=tag_chunker()
    from rag.chunking.tag import TagConfig
    text=(repo_root/"test/fixtures/phase6/tags-original.txt").read_text()
    chunks=list(chunker([ParsedBlock(text)],TagConfig()))
    assert len(chunks)==1 and chunks[0].text==text
    weights={item.label:item.weight for item in chunks[0].tags}
    assert weights["lighthouse"] / weights["calibration"] == pytest.approx(4/5)
    assert sum(v*v for v in weights.values()) == pytest.approx(1)
    assert "52 metres" in chunks[0].text and "73 units" in chunks[0].text


def test_tag_cosine_is_exact_for_full_vectors_and_rank_formula_preserves_old_scores():
    from rag.nlp import fusion
    assert hasattr(fusion,"tag_cosine"), "Tag cosine consumer is missing"
    assert fusion.tag_cosine({"a":3,"b":4},{"a":4,"b":3})==pytest.approx(24/25)
    assert fusion.tag_cosine({"a":1},{"a":1,"b":1})==pytest.approx(1/math.sqrt(2))
    assert fusion.tag_cosine({}, {"a":1})==0
    assert fusion.tag_cosine({"a":0},{"a":1})==0
    assert fusion.rank_feature(fusion.tag_cosine({"a":1},{"a":1}),2)==12
    assert fusion.fuse(.6,.8,.3,fusion.rank_feature(None,None))==pytest.approx(.66)
    assert fusion.fuse(.6,.8,.3,fusion.rank_feature(None,2))==pytest.approx(2.66)


def test_tag_normalization_merges_duplicates_and_rejects_nonfinite_or_negative_weights():
    tag_chunker()
    from rag.parsers.tags import normalize_tags
    tags=normalize_tags({" Lighthouse ":3,"LIGHTHOUSE":4,"calibration":5})
    assert set(tags)=={"lighthouse","calibration"} and tags["lighthouse"]/tags["calibration"]==pytest.approx(7/5)
    for value in [float("nan"),float("inf"),-1,True]:
        with pytest.raises(ValueError):
            normalize_tags({"lighthouse":value})
    from rag.chunking.tag import TagConfig
    for value in (0,33,True):
        with pytest.raises(ValueError):
            TagConfig(tag_top_n=value)


def test_tag_and_pagerank_have_real_index_producers(repo_root):
    from rag.svr.chunk_doc import build_row
    from rag.chunking.tag import TagConfig
    text=(repo_root/"test/fixtures/phase6/tags-original.txt").read_text()
    item=list(tag_chunker()([ParsedBlock(text)],TagConfig()))[0]
    args=dict(index=0,doc_id="d"*32,kb_id="a"*32,doc_name="original.txt",task_id="t"*32,from_page=0,to_page=1,vector=[1.0],enabled=True)
    row=build_row(item,**args,pagerank=2)
    assert row.get("tag_feas"), "Weighted tags are absent from index rows"
    assert row["pagerank_fea"]==2
    assert set(row["tags_kwd"])=={tag.label for tag in item.tags}
    assert "pagerank_fea" not in build_row(item,**args,pagerank=0)
    from rag.svr.failure import TaskFailure
    for invalid in (True,-1,101):
        with pytest.raises(TaskFailure):
            build_row(item,**args,pagerank=invalid)


def test_retriever_consumes_tag_cosine_and_pagerank_before_and_after_rerank():
    from test.unit_test.test_retriever_unit import RecordingStore, hit, result, request, retriever
    row=hit("c1",text="lighthouse")
    row.update(tag_feas={"lighthouse":.6,"calibration":.8},pagerank_fea=2)
    for reranker,expected in [(None,9),(lambda question,texts:[.5],8.85)]:
        store=RecordingStore([result(row),result(hit("c1",text="lighthouse",score=1))])
        output=retriever(store).retrieve(request(question="lighthouse"),reranker=reranker)
        assert output.hits[0].similarity==pytest.approx(expected)
        assert "tag_feas" in store.calls[0]["select"] and store.writes==0


@pytest.mark.parametrize("method,path",[("GET","/api/v1/datasets/<dataset_id>/tags"),("DELETE","/api/v1/datasets/<dataset_id>/tags"),("GET","/api/v1/datasets/tags/aggregation")])
def test_tag_route_has_an_actual_private_handler(method,path):
    from api.apps import create_app
    app=create_app()
    assert any(rule.rule==path and method in rule.methods for rule in app.url_map.iter_rules()),"Tag service route is missing"
