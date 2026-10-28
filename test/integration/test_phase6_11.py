"""Paper passes through real native/service/provider/index paths."""
import pytest
from test.integration import test_pipeline_failures as base
from test.helpers.ingest import add_document,add_task,run_task,indexed
from test.helpers.uploads import sql

_bound_database=base._bound_database
registry=base.registry
fake=base.fake
world=base.world
pytestmark=pytest.mark.integration


@pytest.mark.parametrize('suffix',['md','pdf'])
def test_real_paper_sections_and_cross_page_method_evidence(world,fake,repo_root,suffix):
    path=repo_root/f'test/fixtures/phase6/paper-original.{suffix}'
    doc=add_document(world,path.name,path.read_bytes(),parser_config={'layout_recognize':False,'chunk_token_num':512})
    sql('UPDATE `document` SET `parser_id`=%s WHERE `id`=%s',('paper',doc))
    fake.reset()
    result=run_task(world,add_task(doc))
    rows=sorted(indexed(world,doc_id=[doc]),key=lambda r:r['order_int'])
    assert result.chunk_count==5
    assert [r['section_paths_kwd'] for r in rows]==[['Abstract'],['1 Introduction'],['2 Methods'],['2 Methods / 2.1 Measurements'],['References']]
    assert all(fact in row['content_with_weight'] for fact,row in zip(['52 metres','9100 kilograms','73 units','730 maps','881'],rows,strict=True))
    assert 'introduction of methods in body text' in rows[2]['content_with_weight']
    if suffix=='pdf':
        assert '413' in rows[2]['content_with_weight']
        assert {p[0] for p in rows[2]['position_int']}=={1,2}
    calls=fake.hits('/v1/embeddings')
    assert len(calls)==1 and calls[0].body['input']==[r['content_with_weight'] for r in rows]
