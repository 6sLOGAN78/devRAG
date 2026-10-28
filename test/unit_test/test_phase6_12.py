"""Legal ancestry and Chinese dictionary normalization retain original citation spans."""

import json, hashlib
import pytest
from rag.chunking import factory
from rag.parsers.router import parser_for_suffix
from rag.parsers.types import SourceFile, ParseReport, ParsedBlock, PageBox
from rag.nlp.tokenizer import tokenize, fine_grained_tokenize

pytestmark = pytest.mark.unit


def laws(blocks, size=512):
    assert factory.available("laws"), "Laws implementation is missing"
    return list(factory.get_chunker("laws")(blocks, factory.get_chunker_config("laws", {"chunk_token_num": size})))


def test_original_articles_keep_chapter_ancestry_and_quoted_article_stays_body(repo_root):
    p = repo_root / "test/fixtures/phase6/laws-original.txt"
    gold = json.loads(p.with_name("laws-original-annotation.json").read_text())
    assert hashlib.sha256(p.read_bytes()).hexdigest() == gold["sha256"]
    blocks = parser_for_suffix("txt").load().parse(SourceFile(p, "txt", p.stat().st_size), ParseReport())
    chunks = laws(blocks)
    assert len(chunks) == 3
    assert [list(c.sections[0].path) for c in chunks] == gold["paths"]
    assert all(f in c.text for f, c in zip(gold["facts"], chunks, strict=True))
    assert "引用「第二條」不代表新的條文。" in chunks[0].text
    assert "档案" not in chunks[0].text and "檔案" in chunks[0].text


def test_traditional_simplified_dictionary_queries_match_without_altering_english():
    assert tokenize("檔案保存期限") == tokenize("档案保存期限")
    assert "保存期限" in tokenize("檔案保存期限") or "期限" in tokenize("檔案保存期限")
    assert tokenize("Customer Refund Policy 2024") == ["customer", "refund", "policy", "2024"]
    assert fine_grained_tokenize("camelCaseName_v2") == ["camel", "case", "name", "v", "2"]
    assert fine_grained_tokenize("檔案") == fine_grained_tokenize("档案")


def test_normalized_tokens_expose_original_offsets_after_width_combining_and_links():
    from rag.nlp import tokenizer

    assert hasattr(tokenizer, "tokenize_with_offsets"), "Token source offsets are missing"
    text = "ＡＢＣ cafe\u0301 https://example.invalid/x 檔案 檔案 a@b.com １２３"
    spans = tokenizer.tokenize_with_offsets(text)
    assert all(0 <= s.start < s.end <= len(text) for s in spans)
    assert [text[s.start : s.end] for s in spans if s.text == "abc"] == ["ＡＢＣ"]
    assert [text[s.start : s.end] for s in spans if s.text == "café"] == ["cafe\u0301"]
    assert [text[s.start : s.end] for s in spans if s.text == "档案"] == ["檔案", "檔案"]
    assert [text[s.start : s.end] for s in spans if s.text == "123"] == ["１２３"]
    assert not any("https" in s.text or "@" in s.text or s.text == "com" for s in spans)


def test_english_article_item_hierarchy_long_sections_keep_parent_and_positions():
    box = PageBox(2, 1, 2, 30, 40)
    chunks = laws(
        [
            ParsedBlock("Chapter 1 Records"),
            ParsedBlock("Section 1 Retention"),
            ParsedBlock("Article 3 Period"),
            ParsedBlock("Item 1 Evidence"),
            ParsedBlock("measured value " * 200 + "END73", boxes=(box,), page_sizes={2: (600, 800)}),
        ],
        60,
    )
    assert len(chunks) > 3 and all(c.token_num <= 60 for c in chunks)
    assert all(c.sections[0].path == ("Chapter 1 Records", "Section 1 Retention", "Article 3 Period", "Item 1 Evidence") for c in chunks)
    assert all(c.positions == (box,) for c in chunks) and "END73" in chunks[-1].text


def test_scientific_heading_words_do_not_split_legal_articles():
    chunks = laws([ParsedBlock("Article 1 Scope"), ParsedBlock("First legal fact 52."), ParsedBlock("Methods"), ParsedBlock("Still the same article 73.")])
    assert len(chunks) == 1 and "Methods" in chunks[0].text


def test_laws_model_context_refuses_before_provider(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from rag.svr.embedding import EmbedRunner
    from rag.svr.failure import TaskFailure

    calls = []
    runner = EmbedRunner(SimpleNamespace(), SimpleNamespace(embed_limiter=nullcontext()))
    monkeypatch.setattr(runner, "_bundle", lambda *a: SimpleNamespace(token_limit=3, encode=lambda text: (calls.append(text) or [[1.0]], 0)))
    monkeypatch.setattr("rag.svr.embedding.release_database_connection", lambda: None)
    with pytest.raises(TaskFailure) as error:
        runner._encode_blocking(["word " * 10], SimpleNamespace(parser_id="laws"), 1)
    assert error.value.code == "chunk_too_long" and calls == []


def test_laws_schedules_pdf_once_for_cross_page_article_ancestry(monkeypatch):
    from types import SimpleNamespace
    from api.db.services import ingestion_service

    monkeypatch.setattr(ingestion_service, "pdf_page_count", lambda *a, **k: 30)
    doc = SimpleNamespace(id="a" * 32, suffix="pdf", location="blob", content_hash="hash", parser_id="laws", parser_config={"pages": [[2, 4], [13, 30]]})
    assert ingestion_service._page_ranges(SimpleNamespace(ingest=SimpleNamespace(task_page_size=12)), object(), doc) == [(0, 30)]


def test_index_offsets_point_to_original_traditional_and_fullwidth_source():
    from rag.svr.chunk_doc import build_row
    from rag.chunking.types import Chunk

    text = "ＡＢＣ 檔案保存期限為七十三年"
    row = build_row(Chunk(text, (), {}, 20, 0), index=0, doc_id="a" * 32, kb_id="b" * 32, doc_name="law.txt", task_id="c" * 32, from_page=0, to_page=1000000, vector=[1.0], enabled=True)
    assert "content_token_offsets_int" in row
    terms = row["content_ltks"].split()
    spans = row["content_token_offsets_int"]
    assert len(terms) == len(spans)
    assert text[slice(*spans[terms.index("abc")])] == "ＡＢＣ"
    assert text[slice(*spans[terms.index("档案")])] == "檔案"


def test_legal_headings_inside_multiline_pdf_block_keep_article_boundaries():
    box = PageBox(2, 1, 2, 30, 40)
    chunks = laws([ParsedBlock("第一章 檔案管理\n第一條 保存\n期限為七十三年。\n第二條 公開\n資料為九千一百份。", boxes=(box,))])
    assert len(chunks) == 2
    assert chunks[0].sections[0].path == ("第一章 檔案管理", "第一條 保存")
    assert chunks[1].sections[0].path == ("第一章 檔案管理", "第二條 公開")
    assert all(c.positions and all(b == box for b in c.positions) for c in chunks)


def test_laws_empty_structural_blocks_and_excessive_ancestry():
    from rag.chunking.errors import ChunkTooLong

    assert laws([]) == []
    chunks = laws([ParsedBlock("Article 1 Scope"), ParsedBlock("first fact"), ParsedBlock("Article 2 Example", kind="code"), ParsedBlock("same article")])
    assert len(chunks) == 1 and chunks[0].sections[0].path == ("Article 1 Scope",)
    assert "Article 2 Example" in chunks[0].text
    with pytest.raises(ChunkTooLong):
        laws([ParsedBlock("Chapter 1 Very long parent"), ParsedBlock("Article 1 More ancestry"), ParsedBlock("body")], size=2)


def test_dictionary_terms_and_punctuation_have_stable_source_spans():
    from rag.nlp.tokenizer import tokenize_with_offsets

    text = "中华人民共和国；檔案，保存期限。"
    spans = tokenize_with_offsets(text)
    assert any(len(span.text) > 2 for span in spans)
    assert all("；" not in span.text and "，" not in span.text and "。" not in span.text for span in spans)
    assert all(0 <= span.start < span.end <= len(text) for span in spans)
