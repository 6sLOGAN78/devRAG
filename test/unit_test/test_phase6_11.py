"""Paper boundaries follow standalone headings, preserve source and bound every chunk."""
import hashlib
import json
from contextlib import nullcontext
from types import SimpleNamespace
import pytest
from rag.chunking import factory
from rag.parsers.types import ParsedBlock,PageBox,SourceFile,ParseReport
from rag.parsers.router import parser_for_suffix

pytestmark=pytest.mark.unit


def paper(blocks,size=512):
    assert factory.available('paper'),'Paper implementation is missing'
    return list(factory.get_chunker('paper')(blocks,factory.get_chunker_config('paper',{'chunk_token_num':size})))


def test_original_sections_and_numbered_ancestry_without_body_keyword_split(repo_root):
    root=repo_root/'test/fixtures/phase6'
    gold=json.loads((root/'paper-original-annotation.json').read_text())
    for name,digest in gold['sha256'].items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest
    p=root/'paper-original.md'
    blocks=list(parser_for_suffix('md').load().parse(SourceFile(p,'md',p.stat().st_size),ParseReport()))
    chunks=paper(blocks)
    assert len(chunks)==5
    assert [c.sections[0].path[-1] for c in chunks]==gold['sections']
    assert chunks[3].sections[0].path==('2 Methods','2.1 Measurements')
    assert all(f in c.text for f,c in zip(gold['facts'],chunks,strict=True))
    assert [c.index for c in chunks]==list(range(5))
    assert chunks==paper(blocks)


def test_recognized_headings_are_whole_lines_not_body_keywords():
    chunks=paper([ParsedBlock('Abstract'),ParsedBlock('Fact 52.'),ParsedBlock('1 Introduction'),ParsedBlock('We discuss Methods and References in this sentence.'),ParsedBlock('2 Methods'),ParsedBlock('Fact 73.'),ParsedBlock('2.1 Measurements'),ParsedBlock('Fact 730.'),ParsedBlock('References'),ParsedBlock('Citation 881.')])
    assert len(chunks)==5
    assert 'We discuss Methods and References' in chunks[1].text
    assert chunks[3].text.startswith('2 Methods\n2.1 Measurements\n')


@pytest.mark.parametrize('label',['摘要','引言','方法','参考文献','Abstract','References'])
def test_missing_abstract_multilingual_and_references_only_work(label):
    chunks=paper([ParsedBlock(label),ParsedBlock('原文 52 source.')])
    assert len(chunks)==1 and chunks[0].text.startswith(label+'\n')
    assert chunks[0].sections[0].path==(label,)


def test_long_sections_keep_parent_and_geometry_across_pages():
    boxes=(PageBox(1,1,2,30,40),PageBox(2,1,2,30,40))
    blocks=[ParsedBlock('2 Methods'),ParsedBlock('measured value '*200+'FINAL FACT 73',boxes=boxes,page_sizes={1:(600,800),2:(600,800)},line_range=(2,5)),ParsedBlock('References'),ParsedBlock('Citation881')]
    chunks=paper(blocks,60)
    assert len(chunks)>3 and all(c.token_num<=60 for c in chunks)
    assert all(c.text.startswith('2 Methods\n') and c.positions==boxes and c.source_lines==((2,5),) for c in chunks[:-1])
    assert 'FINAL FACT 73' in chunks[-2].text and chunks[-1].text.startswith('References\n')


def test_typed_noncanonical_headings_tables_images_and_ties_keep_source():
    from rag.parsers.tables import Table,TableCell
    table=Table(1,1,(TableCell(0,0,'52'),),asset_id='a'*32)
    blocks=[ParsedBlock('Unusual experiment','heading',heading_level=1),ParsedBlock('Phase A','heading',heading_level=2),ParsedBlock('52','table',table=table,image_ids=('a'*32,),boxes=(PageBox(1,1,2,3,4),)),ParsedBlock('Phase B','heading',heading_level=2),ParsedBlock('9100')]
    chunks=paper(blocks)
    assert len(chunks)==2 and chunks[0].sections[0].path==('Unusual experiment','Phase A')
    assert chunks[1].sections[0].path==('Unusual experiment','Phase B')
    assert chunks[0].tables==(table,) and chunks[0].image_ids==('a'*32,) and chunks[0].positions==blocks[2].boxes


def test_paper_actual_model_context_refuses_before_encode(monkeypatch):
    from rag.svr.embedding import EmbedRunner
    from rag.svr.failure import TaskFailure
    calls=[]
    runner=EmbedRunner(SimpleNamespace(),SimpleNamespace(embed_limiter=nullcontext()))
    monkeypatch.setattr(runner,'_bundle',lambda *a:SimpleNamespace(token_limit=3,encode=lambda text:(calls.append(text) or [[1.0]],0)))
    monkeypatch.setattr('rag.svr.embedding.release_database_connection',lambda:None)
    with pytest.raises(TaskFailure) as error:
        runner._encode_blocking(['word '*10],SimpleNamespace(parser_id='paper'),1)
    assert error.value.code=='chunk_too_long' and calls==[]


def test_paper_schedules_whole_pdf_so_sections_do_not_reset_at_task_boundaries(monkeypatch):
    from api.db.services import ingestion_service
    monkeypatch.setattr(ingestion_service,'pdf_page_count',lambda *a,**k:30)
    doc=SimpleNamespace(id='a'*32,suffix='pdf',location='blob',content_hash='hash',parser_id='paper',parser_config={'pages':[[2,4],[13,30]]})
    assert ingestion_service._page_ranges(SimpleNamespace(ingest=SimpleNamespace(task_page_size=12)),object(),doc)==[(0,30)]


@pytest.mark.parametrize('kind',['code','table','list'])
def test_heading_words_inside_structural_blocks_remain_source_body(kind):
    chunks=paper([ParsedBlock('1 Introduction'),ParsedBlock('Fact 52.'),ParsedBlock('Methods',kind),ParsedBlock('Fact 73.')])
    assert len(chunks)==1 and 'Methods' in chunks[0].text and '73' in chunks[0].text


def test_setext_markdown_heading_keeps_clean_section_label(tmp_path):
    p=tmp_path/'setext.md';p.write_text('Abstract\n========\n\nFact52\n\nMethods\n-------\n\nFact73\n')
    blocks=list(parser_for_suffix('md').load().parse(SourceFile(p,'md',p.stat().st_size),ParseReport()))
    chunks=paper(blocks)
    assert [c.sections[0].path[-1] for c in chunks]==['Abstract','Methods']
