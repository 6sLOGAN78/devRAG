"""Real EPUB worker/provider/index and bounded invalid archive refusal."""
import json
import pytest
from test.integration import test_pipeline_failures as base
from test.helpers.ingest import add_document, add_task, run_task, indexed
from test.helpers.uploads import sql

_bound_database=base._bound_database
registry=base.registry
fake=base.fake
world=base.world
pytestmark=pytest.mark.integration


def test_real_book_keeps_spine_paths_source_and_retry_ids(world,fake,repo_root):
    path=repo_root/'test/fixtures/phase6/book-original.epub'
    gold=json.loads(path.with_name('book-original-annotation.json').read_text())
    doc=add_document(world,path.name,path.read_bytes())
    sql('UPDATE `document` SET `parser_id`=%s WHERE `id`=%s',('book',doc))
    task=add_task(doc)
    fake.reset()
    result=run_task(world,task)
    assert result.chunk_count==2
    rows=sorted(indexed(world,doc_id=[doc]),key=lambda r:r['order_int'])
    assert [r['source_paths_kwd'][0] for r in rows]==gold['spine']
    assert all(fact in row['content_with_weight'] for fact,row in zip(gold['facts'],rows,strict=True))
    assert rows[0]['content_with_weight'].startswith('Field guide\nCoast\nLighthouse\nMeasurements\n')
    assert all(not row['position_int'] for row in rows)
    calls=fake.hits('/v1/embeddings')
    assert len(calls)==1 and calls[0].body['input']==[r['content_with_weight'] for r in rows]
    again=run_task(world,task)
    retried=sorted(indexed(world,doc_id=[doc]),key=lambda r:r['order_int'])
    assert again.chunk_count==2 and [r['id'] for r in rows]==[r['id'] for r in retried]
    assert [r['content_with_weight'] for r in rows]==[r['content_with_weight'] for r in retried]


def test_damaged_book_refuses_before_provider_and_index(world,fake):
    from rag.svr.failure import TaskFailure
    doc=add_document(world,'damaged.epub',b'PK\x03\x04damaged EPUB central directory')
    sql('UPDATE `document` SET `parser_id`=%s WHERE `id`=%s',('book',doc))
    fake.reset()
    with pytest.raises(TaskFailure) as failure:
        run_task(world,add_task(doc))
    assert failure.value.code=='file_damaged'
    assert fake.hits('/v1/embeddings')==[] and indexed(world,doc_id=[doc])==[]
