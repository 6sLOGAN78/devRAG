"""Original MIME fixture and envelope/body boundaries precede implementation."""

import json
from pathlib import Path
from email.message import EmailMessage

import pytest

pytestmark = pytest.mark.unit


def parse_file(path, **kwargs):
    from rag.parsers.router import parseable, parser_for_suffix
    from rag.parsers.types import SourceFile, ParseReport
    assert parseable("eml"), "Email parser is missing"
    report = ParseReport()
    blocks = list(parser_for_suffix("eml").load().parse(SourceFile(path, "eml", path.stat().st_size), report, **kwargs))
    return blocks, report


def test_original_email_preserves_decoded_envelope_and_selects_plain_body(repo_root):
    path = repo_root / "test/fixtures/phase6/email-original.eml"
    annotation = json.loads(path.with_name("email-original-annotation.json").read_text())
    blocks, report = parse_file(path)
    assert "".join(block.text for block in blocks).strip() == annotation["body"].strip()
    envelope = blocks[0].email
    assert envelope.subject == annotation["subject"] and "alice@example.test" in envelope.sender
    assert envelope.recipients.count("bob@example.test") == 1 and "chen@example.test" in envelope.recipients
    assert envelope.date == annotation["date"] and envelope.message_id == annotation["message_id"]
    assert len(envelope.attachments) == 2
    assert all(not block.boxes and not block.page_sizes for block in blocks)
    assert all(trap not in "".join(b.text for b in blocks) for trap in annotation["must_not_index"])
    assert any("2 attachment" in note for note in report.notes)


def test_email_chunker_repeats_envelope_and_real_mime_provenance(repo_root):
    from rag.chunking.factory import available, get_chunker, get_chunker_config
    assert available("email"), "Email chunker is missing"
    blocks, _ = parse_file(repo_root / "test/fixtures/phase6/email-original.eml")
    chunks = list(get_chunker("email")(blocks, get_chunker_config("email", {"chunk_token_num":256})))
    assert len(chunks) > 1
    for chunk in chunks:
        assert "From: 研究员" in chunk.text and "alice@example.test" in chunk.text
        assert "To: bob@example.test, chen@example.test" in chunk.text
        assert "Subject: 灯塔 calibration facts" in chunk.text
        assert "Date: Thu, 29 Oct 2026 10:15:00 +0530" in chunk.text
        assert "MIME part:" in chunk.text and "Ignored attachment:" in chunk.text
        assert chunk.positions == () and not chunk.page_sizes and chunk.token_num <= 256
    assert any("52 metres" in chunk.text and "73 units" in chunk.text for chunk in chunks)


def test_html_only_message_is_inert_and_invalid_date_is_retained(tmp_path):
    msg = EmailMessage()
    msg["Subject"] = "HTML-only calibration"
    msg["Date"] = "not a date"
    msg.set_content('<p>Calibration 73 units.</p><script>EXECUTION_TRAP</script><img src="https://untrusted.invalid/image"/>',subtype="html")
    path = tmp_path / "message.eml"
    path.write_bytes(msg.as_bytes().replace(b"Date:\n", b"Date: not a date\n", 1))
    blocks, report = parse_file(path)
    assert "Calibration 73 units." in "".join(b.text for b in blocks)
    assert "EXECUTION_TRAP" not in "".join(b.text for b in blocks)
    assert blocks[0].email.sender == "" and blocks[0].email.date == "not a date"
    assert any("date" in note.lower() for note in report.notes)


def test_email_native_defaults_and_operator_allowlist_are_honest():
    from common.settings import DEFAULT_UPLOAD_EXTENSIONS, UploadSettings
    from api.db.services.upload_rules import validate_file
    from api.db.services.service_errors import ServiceError
    assert "eml" in DEFAULT_UPLOAD_EXTENSIONS, "Email upload support is missing"
    content = b"Subject: Original\r\n\r\nCalibration 73 units."
    assert validate_file("message.eml","message/rfc822",content,len(content),UploadSettings()).extension == "eml"
    with pytest.raises(ServiceError):
        validate_file("message.eml","application/pdf",content,len(content),UploadSettings())
    with pytest.raises(ServiceError):
        validate_file("message.eml","message/rfc822",content,len(content),UploadSettings(allowed_extensions=("txt",)))


def test_email_limits_nesting_parts_source_and_decoded_body(tmp_path):
    from rag.parsers.types import ParseLimits
    from rag.parsers.errors import FileTooLarge

    leaf = EmailMessage()
    leaf.set_content("Original calibration 73 units.")
    nested = leaf
    for _ in range(18):
        outer = EmailMessage()
        outer.make_mixed()
        outer.attach(nested)
        nested = outer
    path = tmp_path / "bounded.eml"
    path.write_bytes(nested.as_bytes())
    with pytest.raises(FileTooLarge):
        parse_file(path)
    wide = EmailMessage()
    wide.make_mixed()
    for _ in range(130):
        wide.attach(leaf)
    path.write_bytes(wide.as_bytes())
    with pytest.raises(FileTooLarge):
        parse_file(path)
    path.write_bytes(b"Subject: Original\r\n\r\n" + b"x" * 200)
    with pytest.raises(FileTooLarge):
        parse_file(path, limits=ParseLimits(max_text_bytes=64))
    large = EmailMessage()
    large.set_content("x" * (1024 * 1024 + 1), cte="base64")
    path.write_bytes(large.as_bytes())
    with pytest.raises(FileTooLarge):
        parse_file(path)


@pytest.mark.parametrize("body", [
    b"Content-Type: multipart/mixed\r\n\r\nmissing boundary",
    b"Content-Type: invalid-type\r\n\r\nDo not treat this as an implicit plain body.",
    b"Content-Type: text/plain; charset=unregistered-charset\r\n\r\nOriginal",
    b"Content-Type: text/plain\r\nContent-Transfer-Encoding: base64\r\n\r\n@@@@",
])
def test_malformed_mime_does_not_silently_fall_back_to_body(tmp_path, body):
    from rag.parsers.errors import FileDamaged
    path = tmp_path / "bad.eml"
    path.write_bytes(body)
    with pytest.raises(FileDamaged):
        parse_file(path)


def test_attachment_only_message_refuses_without_indexing_attachment_text(tmp_path):
    from rag.parsers.errors import NoReadableText
    message = EmailMessage()
    message.add_attachment(b"ATTACHMENT_TRAP9999", maintype="application", subtype="octet-stream", filename="../../escape.txt")
    path = tmp_path / "attachments.eml"
    path.write_bytes(message.as_bytes())
    with pytest.raises(NoReadableText):
        parse_file(path)


def test_email_chunker_refuses_an_envelope_that_cannot_fit_instead_of_dropping_it(repo_root):
    from rag.chunking.email import chunk, EmailConfig
    from rag.chunking.errors import ChunkTooLong
    blocks, _ = parse_file(repo_root / "test/fixtures/phase6/email-original.eml")
    with pytest.raises(ChunkTooLong):
        list(chunk(blocks, EmailConfig(chunk_token_num=16)))


def test_related_start_selects_named_body_and_mixed_bodies_keep_order(tmp_path):
    message = EmailMessage()
    message.make_mixed()
    intro = EmailMessage()
    intro.set_content("First original section.")
    message.attach(intro)
    related = EmailMessage()
    related.make_related()
    related.set_param("start", "<chosen>")
    trap = EmailMessage()
    trap.set_content("UNSELECTED_RELATED_TRAP")
    trap["Content-ID"] = "<other>"
    related.attach(trap)
    chosen = EmailMessage()
    chosen.set_content("Second original section: calibration 73 units.")
    chosen["Content-ID"] = "<chosen>"
    related.attach(chosen)
    message.attach(related)
    path = tmp_path / "related.eml"
    path.write_bytes(message.as_bytes())
    blocks, _ = parse_file(path)
    assert [b.email.part_path for b in blocks] == ["1.1", "1.2.2"]
    assert blocks[0].text.strip() == "First original section."
    assert blocks[1].text.strip() == "Second original section: calibration 73 units."
    assert all("UNSELECTED_RELATED_TRAP" not in block.text for block in blocks)
