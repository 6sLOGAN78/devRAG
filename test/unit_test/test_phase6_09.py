"""Stable structured records, exact CSV quoting and atomic Q&A without fallback."""

import json
import pytest
from rag.parsers.types import SourceFile, ParseReport
from rag.parsers.router import parser_for_suffix
from rag.chunking import factory

pytestmark = pytest.mark.unit


def parse(path, **options):
    spec = parser_for_suffix(path.suffix)
    if path.suffix in {".json", ".csv"}:
        assert spec.name == path.suffix[1:], "Structured format still routed to TXT"
    return list(spec.load().parse(SourceFile(path, path.suffix[1:], path.stat().st_size), ParseReport(), **options))


def test_csv_bom_quotes_newlines_headers_and_formula_are_literal(repo_root):
    root = repo_root / "test/fixtures/phase6"
    gold = json.loads((root / "qa-original-annotation.json").read_text())
    blocks = parse(root / "qa-original.csv")
    assert len(blocks) == 2
    record = blocks[0].record
    assert record is not None
    assert [f.name for f in record.fields] == ["Question", "Answer", "Source"]
    assert record.fields[1].value == gold["answers"][0]
    assert record.fields[2].value == "=SUM(20,32)"
    assert gold["answers"][0] in blocks[0].text
    assert blocks[0].line_range == (2, 3)


def test_nested_json_records_use_stable_escaped_paths(repo_root, tmp_path):
    blocks = parse(repo_root / "test/fixtures/phase6/qa-original.json")
    assert len(blocks) == 2
    assert [f.path for f in blocks[0].record.fields] == ["/0/answer", "/0/metadata/number", "/0/metadata/site", "/0/question"]
    p = tmp_path / "paths.json"
    p.write_text('{"a/b":{"~key":52},"z":9100}')
    assert [f.path for f in parse(p)[0].record.fields] == ["/a~1b/~0key", "/z"]


@pytest.mark.parametrize("suffix", ["csv", "json", "xlsx", "txt"])
def test_qa_preserves_exact_pair_text_and_question_tokens(repo_root, suffix):
    assert factory.available("qa"), "Q&A implementation is missing"
    root = repo_root / "test/fixtures/phase6"
    gold = json.loads((root / "qa-original-annotation.json").read_text())
    blocks = parse(root / f"qa-original.{suffix}", **({"structured_records": True} if suffix == "xlsx" else {}))
    chunks = list(factory.get_chunker("qa")(blocks, factory.get_chunker_config("qa", {"chunk_token_num": 1})))
    assert len(chunks) == 2
    assert [c.question for c in chunks] == gold["questions"]
    assert all(a in c.text for a, c in zip(gold["answers"], chunks, strict=True))
    from rag.svr.chunk_doc import build_row

    row = build_row(chunks[0], index=0, doc_id="d" * 32, kb_id="b" * 32, doc_name="record." + suffix, task_id="t" * 32, from_page=0, to_page=1, vector=[1.0], enabled=True)
    assert row["question_tks"] == "what is the lighthouse height"


@pytest.mark.parametrize("body", ["Question,Question\nA,B\n", "Question,Answer\nOnly one\n", 'Question,Answer\n"unclosed,52\n'])
def test_bad_csv_structure_refuses_instead_of_txt_fallback(tmp_path, body):
    from rag.parsers.errors import ParserError

    p = tmp_path / "bad.csv"
    p.write_text(body)
    with pytest.raises(ParserError):
        parse(p)


@pytest.mark.parametrize("body", ['{"x":1,"x":2}', "[" * 40 + "0" + "]" * 40, '{"question":NaN}'])
def test_bad_json_duplicates_depth_or_nonfinite_values_refuse(tmp_path, body):
    from rag.parsers.errors import ParserError

    p = tmp_path / "bad.json"
    p.write_text(body)
    with pytest.raises(ParserError):
        parse(p)


@pytest.mark.parametrize("body", ["Question,Answer\n,52\n", "Question,Answer\nHow tall?,\n", "Question,Q,Answer\nHow tall?,Other?,52\n"])
def test_invalid_or_ambiguous_qa_pairs_fail_before_emitting(tmp_path, body):
    assert factory.available("qa"), "Q&A implementation is missing"
    from rag.chunking.errors import InvalidPair

    p = tmp_path / "bad.csv"
    p.write_text(body)
    with pytest.raises(InvalidPair):
        list(factory.get_chunker("qa")(parse(p), factory.get_chunker_config("qa", {})))


def test_xlsx_date_metadata_remains_a_literal_scalar(repo_root, tmp_path):
    from datetime import datetime
    from test.helpers.office_files import make_xlsx

    p = tmp_path / "dates.xlsx"
    p.write_bytes(make_xlsx({"Facts": [["Question", "Answer", "Measured"], ["What height?", "52 metres", datetime(2026, 10, 28, 12, 30)]]}))
    blocks = parse(p, structured_records=True)
    assert next(f.value for f in blocks[0].record.fields if f.name == "Measured") == "2026-10-28T12:30:00"


def test_json_record_limit_refuses_without_partial_records(tmp_path):
    from rag.parsers.errors import FileTooLarge

    p = tmp_path / "many.json"
    p.write_text(json.dumps([0] * 10001))
    with pytest.raises(FileTooLarge):
        parse(p)


def test_csv_field_limit_is_bounded_before_qa(tmp_path):
    from rag.parsers.errors import FileTooLarge

    p = tmp_path / "wide.csv"
    p.write_text("Question,Answer\nHow tall?," + "a" * 65537 + "\n")
    with pytest.raises(FileTooLarge):
        parse(p)


def test_explicit_question_without_answer_is_not_a_generic_chunk(tmp_path):
    from rag.chunking.errors import InvalidPair

    p = tmp_path / "missing.txt"
    p.write_text("Question: What height?\nNo answer marker here.")
    with pytest.raises(InvalidPair):
        list(factory.get_chunker("qa")(parse(p), factory.get_chunker_config("qa", {})))


def test_qa_does_not_split_an_oversize_record(tmp_path):
    from rag.chunking.errors import ChunkTooLong

    p = tmp_path / "large.csv"
    p.write_text("Question,Answer\nWhat height?," + "word " * 9000 + "\n")
    with pytest.raises(ChunkTooLong):
        list(factory.get_chunker("qa")(parse(p), factory.get_chunker_config("qa", {})))


def test_qa_rejects_unsupported_pdf_before_loading_native_or_reading_source(tmp_path):
    from types import SimpleNamespace
    from rag.svr.pipeline import _parse_and_chunk
    from rag.parsers.errors import UnsupportedType

    with pytest.raises(UnsupportedType):
        _parse_and_chunk(SimpleNamespace(parser_id="qa", doc_suffix="pdf"), None, None, tmp_path / "missing.pdf", ParseReport())


def test_qa_checks_the_actual_model_context_before_encode(monkeypatch):
    from types import SimpleNamespace
    from contextlib import nullcontext
    from rag.svr.embedding import EmbedRunner
    from rag.svr.failure import TaskFailure

    calls = []
    bundle = SimpleNamespace(token_limit=3, encode=lambda values: (calls.append(values) or [[1.0]], 0))
    runner = EmbedRunner(SimpleNamespace(), SimpleNamespace(embed_limiter=nullcontext()))
    monkeypatch.setattr(runner, "_bundle", lambda *args: bundle)
    monkeypatch.setattr("rag.svr.embedding.release_database_connection", lambda: None)
    with pytest.raises(TaskFailure) as failure:
        runner._encode_blocking(["word " * 10], SimpleNamespace(parser_id="qa"), 1)
    assert failure.value.code == "chunk_too_long" and calls == []


def test_original_structured_sources_match_the_frozen_annotation(repo_root):
    import hashlib

    root = repo_root / "test/fixtures/phase6"
    annotation = json.loads((root / "qa-original-annotation.json").read_text())
    assert all(hashlib.sha256((root / name).read_bytes()).hexdigest() == digest for name, digest in annotation["sha256"].items())
