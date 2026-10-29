"""Original .eml upload and Email chunks against actual storage, SQL and index."""

import json
import pytest
from test.integration import test_pipeline_failures as base
from test.helpers.ingest import add_document, add_task, run_task, indexed
from test.helpers.uploads import sql

_bound_database = base._bound_database
registry = base.registry
fake = base.fake
world = base.world
pytestmark = pytest.mark.integration


def test_real_email_upload_and_index_preserve_decoded_envelope_and_body(world, repo_root):
    path = repo_root / "test/fixtures/phase6/email-original.eml"
    annotation = json.loads(path.with_name("email-original-annotation.json").read_text())
    doc = add_document(world, path.name, path.read_bytes())
    sql("UPDATE `document` SET `parser_id`='email', `parser_config`=%s WHERE `id`=%s", ('{"chunk_token_num":256}', doc))
    result = run_task(world, add_task(doc))
    rows = sorted(indexed(world, doc_id=[doc]), key=lambda r: r["order_int"])
    assert result.chunk_count == len(rows) > 1
    for row in rows:
        content = row["content_with_weight"]
        assert "From: 研究员" in content and "To: bob@example.test, chen@example.test" in content
        assert "Subject: 灯塔 calibration facts" in content and "Date: Thu, 29 Oct 2026 10:15:00 +0530" in content
        assert "MIME part: 1.1.1" in content and "Ignored attachment: ../calibration-secret.txt" in content
        assert row["position_int"] == [] and row["doc_id"] == doc
        assert all(trap not in content for trap in annotation["must_not_index"])
    assert any("52 metres" in row["content_with_weight"] and "73 units" in row["content_with_weight"] for row in rows)


def test_email_method_refuses_an_unstructured_source_without_falling_back(world):
    from rag.svr.failure import TaskFailure
    from test.helpers.office_files import make_docx

    doc = add_document(world, "ordinary.docx", make_docx(["This is not an email envelope."]))
    sql("UPDATE `document` SET `parser_id`='email' WHERE `id`=%s", (doc,))
    with pytest.raises(TaskFailure) as failure:
        run_task(world, add_task(doc))
    assert failure.value.code == "no_readable_text"
    assert indexed(world, doc_id=[doc]) == []
