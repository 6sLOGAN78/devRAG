"""Original EPUB spine order, ancestry, bounded archive/XML and Book source contract."""
import hashlib
import json
import stat
import zipfile
from pathlib import Path
import pytest
from rag.chunking import factory
from rag.parsers.router import parser_for_suffix, parseable
from rag.parsers.types import SourceFile, ParseReport, ParseLimits, ParsedBlock, PageBox
from rag.parsers.errors import FileDamaged, ArchiveLimitsExceeded, NoReadableText

pytestmark = pytest.mark.unit


def parse(path, limits=None):
    assert parseable('epub'), 'EPUB parsing is not implemented'
    report = ParseReport()
    blocks = list(parser_for_suffix('epub').load().parse(SourceFile(path, 'epub', path.stat().st_size), report, limits=limits))
    return blocks, report


def book(blocks, size=512):
    assert factory.available('book'), 'Book chunking is not implemented'
    return list(factory.get_chunker('book')(blocks, factory.get_chunker_config('book', {'chunk_token_num':size})))


def altered(repo_root, tmp_path, changes):
    with zipfile.ZipFile(repo_root/'test/fixtures/phase6/book-original.epub') as z:
        members = {n: z.read(n) for n in z.namelist()}
    for name, value in changes.items():
        if value is None:
            members.pop(name)
        else:
            members[name] = value.encode() if isinstance(value,str) else value
    path = tmp_path/'altered.epub'
    with zipfile.ZipFile(path, 'w') as z:
        for name, value in members.items():
            z.writestr(name, value)
    return path


def test_original_spine_beats_zip_order_and_preserves_toc_ancestry(repo_root):
    p=repo_root/'test/fixtures/phase6/book-original.epub'
    gold=json.loads(p.with_name('book-original-annotation.json').read_text())
    assert hashlib.sha256(p.read_bytes()).hexdigest()==gold['sha256']
    blocks, report=parse(p)
    chapters=list(dict.fromkeys(b.section.source_path for b in blocks))
    assert chapters==gold['spine']
    first=next(b for b in blocks if '52 metres' in b.text)
    assert first.section.path==('Field guide','Coast','Lighthouse','Measurements')
    assert all(not b.boxes for b in blocks) and report.pages_total is None
    text='\n'.join(b.text for b in blocks)
    assert all(f in text for f in gold['facts'])
    assert 'epubExecuted' not in text and 'Not chapter text' not in text


def test_book_repeats_parent_prefix_keeps_chapters_separate_and_ids_deterministic(repo_root):
    from rag.svr.chunk_doc import build_row
    blocks,_=parse(repo_root/'test/fixtures/phase6/book-original.epub')
    chunks=book(blocks)
    assert len(chunks)==2
    assert chunks[0].text.startswith('Field guide\nCoast\nLighthouse\nMeasurements\n')
    assert '52 metres' in chunks[0].text and '9100' not in chunks[0].text
    assert chunks[1].text.startswith('Field guide\nOrchard\n') and '9100 kilograms' in chunks[1].text
    assert chunks==book(blocks)
    rows=[build_row(c,index=i,doc_id='a'*32,kb_id='b'*32,doc_name='book.epub',task_id='c'*32,from_page=0,to_page=1000000,vector=[1.0],enabled=True) for i,c in enumerate(chunks)]
    assert [r['id'] for r in rows]==['a'*32+'_0','a'*32+'_1']
    assert rows[0]['source_paths_kwd']==['OPS/z-lighthouse.xhtml']
    assert rows[0]['section_paths_kwd']==['Field guide / Coast / Lighthouse / Measurements']


@pytest.mark.parametrize('change', ['missing','duplicate','unknown','container','namespace','empty'])
def test_damaged_or_empty_epub_refuses(repo_root,tmp_path,change):
    with zipfile.ZipFile(repo_root/'test/fixtures/phase6/book-original.epub') as z:
        opf=z.read('OPS/book.opf').decode()
    changes={
      'missing':{'OPS/z-lighthouse.xhtml':None},
      'duplicate':{'OPS/book.opf':opf.replace('<itemref idref="coast"/>','<itemref idref="coast"/><itemref idref="coast"/>')},
      'unknown':{'OPS/book.opf':opf.replace('idref="coast"','idref="unknown"')},
      'container':{'META-INF/container.xml':'<broken>'},
      'namespace':{'META-INF/container.xml':'<container><rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>'},
      'empty':{'OPS/z-lighthouse.xhtml':'<html xmlns="http://www.w3.org/1999/xhtml"><body/></html>','OPS/a-orchard.xhtml':'<html xmlns="http://www.w3.org/1999/xhtml"><body/></html>'},
    }[change]
    with pytest.raises(NoReadableText if change=='empty' else FileDamaged):
        parse(altered(repo_root,tmp_path,changes))


@pytest.mark.parametrize('name',['../escape','/absolute','OPS/../escape','OPS\\escape','OPS/%2e%2e/escape'])
def test_archive_traversal_entries_refuse_without_extraction(repo_root,tmp_path,name):
    with pytest.raises(FileDamaged):
        parse(altered(repo_root,tmp_path,{name:'secret'}))
    assert not (tmp_path.parent/'escape').exists()


def test_archive_symlink_and_duplicate_members_refuse(repo_root,tmp_path):
    for symlink in (True,False):
        p=altered(repo_root,tmp_path,{})
        with zipfile.ZipFile(p,'a') as z:
            if symlink:
                info=zipfile.ZipInfo('OPS/link');info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(info,'/etc/passwd')
            else:
                with pytest.warns(UserWarning,match='Duplicate'):
                    z.writestr('mimetype','application/epub+zip')
        with pytest.raises(FileDamaged):
            parse(p)


@pytest.mark.parametrize('where',['META-INF/container.xml','OPS/book.opf','OPS/z-lighthouse.xhtml','OPS/nav.xhtml'])
def test_dtd_entities_refuse_even_in_unused_markup(repo_root,tmp_path,where):
    with pytest.raises(FileDamaged):
        parse(altered(repo_root,tmp_path,{where:'<!DOCTYPE html [<!ENTITY secret SYSTEM "file:///etc/passwd">]><html>&secret;</html>'}))


def test_archive_size_ratio_xml_depth_and_text_limits_refuse(repo_root,tmp_path):
    from rag.parsers.errors import FileTooLarge
    p=altered(repo_root,tmp_path,{'OPS/unused.xml':'<r>'+('<a>'*80)+'value'+('</a>'*80)+'</r>'})
    with pytest.raises((FileDamaged,ArchiveLimitsExceeded)):
        parse(p)
    with pytest.raises(FileTooLarge):
        parse(repo_root/'test/fixtures/phase6/book-original.epub',ParseLimits(max_text_bytes=10))
    p=altered(repo_root,tmp_path,{})
    with zipfile.ZipFile(p,'a',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('padding','x'*1000000)
    with pytest.raises(ArchiveLimitsExceeded):
        parse(p)


def test_epub_does_not_fetch_remote_resources(repo_root,monkeypatch):
    import socket,subprocess
    def forbidden(*a,**k):
        raise AssertionError('EPUB attempted network or execution')
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    monkeypatch.setattr(subprocess,'run',forbidden)
    blocks,_=parse(repo_root/'test/fixtures/phase6/book-original.epub')
    assert '52 metres' in '\n'.join(b.text for b in blocks)


def test_non_epub_heading_book_splits_oversize_prose_with_geometry_and_parent():
    blocks=[ParsedBlock('Field guide','heading',heading_level=1),ParsedBlock('Measurements','heading',heading_level=2),ParsedBlock('measured value '*200+'FINAL FACT 73',boxes=(PageBox(2,1,2,3,4),),page_sizes={2:(600,800)},line_range=(4,4))]
    chunks=book(blocks,60)
    assert len(chunks)>3 and all(c.token_num<=60 for c in chunks)
    assert all(c.text.startswith('Field guide\nMeasurements\n') and c.positions==blocks[2].boxes and c.source_lines==((4,4),) for c in chunks)
    assert 'FINAL FACT 73' in chunks[-1].text


def test_book_actual_model_context_refuses_before_encode(monkeypatch):
    from types import SimpleNamespace
    from contextlib import nullcontext
    from rag.svr.embedding import EmbedRunner
    from rag.svr.failure import TaskFailure
    calls=[]
    runner=EmbedRunner(SimpleNamespace(),SimpleNamespace(embed_limiter=nullcontext()))
    monkeypatch.setattr(runner,'_bundle',lambda *a:SimpleNamespace(token_limit=3,encode=lambda text:(calls.append(text) or [[1.0]],0)))
    monkeypatch.setattr('rag.svr.embedding.release_database_connection',lambda:None)
    with pytest.raises(TaskFailure) as error:
        runner._encode_blocking(['word '*10],SimpleNamespace(parser_id='book'),1)
    assert error.value.code=='chunk_too_long' and calls==[]


def test_duplicate_spine_targets_under_different_ids_refuse(repo_root,tmp_path):
    with zipfile.ZipFile(repo_root/'test/fixtures/phase6/book-original.epub') as z:
        opf=z.read('OPS/book.opf').decode().replace('href="a-orchard.xhtml"','href="z-lighthouse.xhtml"')
    with pytest.raises(FileDamaged):
        parse(altered(repo_root,tmp_path,{'OPS/book.opf':opf}))


@pytest.mark.parametrize('href',['https://example.invalid/chapter','../../escape.xhtml','file:///etc/passwd','%2e%2e/%2e%2e/escape.xhtml','chapter.xhtml?token=private'])
def test_unsafe_manifest_addresses_refuse(repo_root,tmp_path,href):
    with zipfile.ZipFile(repo_root/'test/fixtures/phase6/book-original.epub') as z:
        opf=z.read('OPS/book.opf').decode().replace('href="a-orchard.xhtml"','href="'+href+'"')
    with pytest.raises(FileDamaged):
        parse(altered(repo_root,tmp_path,{'OPS/book.opf':opf}))


def test_epub2_ncx_inherited_namespaces_keep_nested_chapter_path(repo_root,tmp_path):
    with zipfile.ZipFile(repo_root/'test/fixtures/phase6/book-original.epub') as z:
        opf=z.read('OPS/book.opf').decode().replace('href="nav.xhtml" properties="nav" media-type="application/xhtml+xml"','href="toc.ncx" media-type="application/x-dtbncx+xml"').replace('<spine>','<spine toc="nav">')
    ncx='<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap><navPoint id="root"><navLabel><text>Guide</text></navLabel><content src="z-lighthouse.xhtml"/><navPoint id="orchard"><navLabel><text>Orchard</text></navLabel><content src="a-orchard.xhtml"/></navPoint></navPoint></navMap></ncx>'
    blocks,_=parse(altered(repo_root,tmp_path,{'OPS/book.opf':opf,'OPS/toc.ncx':ncx}))
    assert next(b.section.path for b in blocks if '9100' in b.text)==('Guide','Orchard')


def test_book_preserves_typed_tables_images_and_source_geometry():
    from rag.parsers.tables import Table,TableCell
    table=Table(1,1,(TableCell(0,0,'52'),),asset_id='a'*32)
    block=ParsedBlock('52','table',boxes=(PageBox(2,1,2,3,4),),page_sizes={2:(600,800)},table=table,image_ids=('a'*32,),line_range=(3,4))
    (chunk,)=book([ParsedBlock('Chapter','heading',heading_level=1),block])
    assert chunk.tables==(table,) and chunk.image_ids==('a'*32,)
    assert chunk.positions==block.boxes and chunk.source_lines==((3,4),)
