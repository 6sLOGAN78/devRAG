"""List rows, detail and the PDF page count against the real MySQL and MinIO (plan 04-15; DOC-12, DOC-20, DOC-23, D-07)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from api.db.database import DB
from api.db.models import PipelineOperationLog
from api.db.services import document_view as view
from api.db.services import knowledgebase_service as kbsvc
from api.db.services import pdf_pages
from api.db.services.service_errors import Kind
from rag.utils.storage_base import Storage
from test.helpers.pdf_files import garbage_bytes, thirteen_page_pdf
from test.helpers.uploads import sql, text_bytes
from test.integration import test_upload_service as base
from test.integration.test_knowledgebase_service import principal_of

pytestmark = pytest.mark.integration

_bound_database = base._bound_database
settings = base.settings
llm = base.llm
registry = base.registry
storage = base.storage
space = base.space
item = base.item
upload = base.upload
refused = base.refused

JPEG = "data:image/jpeg;base64,/9j/4AAQ"
PNG_URL = "data:image/png;base64,iVBORw0K"


def visible_of(owner, dataset):
    return kbsvc.load_visible_dataset(principal_of(owner), dataset.id)


def one(settings, owner, dataset, storage, name="a.txt", data=None):
    return upload(settings, owner, dataset, [item(name, data if data is not None else text_bytes(name))], storage=storage)[0]


def set_doc(doc_id: str, **values: Any) -> None:
    columns = ", ".join(f"`{key}` = %s" for key in values)
    sql(f"UPDATE `document` SET {columns} WHERE `id` = %s", (*values.values(), doc_id))  # noqa: S608  (column names come from the test)


def add_log(owner, dataset, doc: dict, *, status: str, dsl: dict | None = None, msg: str = "", create_time: int | None = None) -> str:
    log_id = uuid.uuid4().hex
    with DB.connection_context():
        extra = {} if create_time is None else {"create_time": create_time}
        PipelineOperationLog.create(
            id=log_id, document_id=doc["id"], tenant_id=owner.tenant_id, kb_id=dataset.id, parser_id="naive", document_name=doc["name"],
            document_suffix=doc["suffix"], document_type=doc["type"], source_from="local", operation_status=status, dsl=dsl or {}, progress_msg=msg, **extra,
        )  # fmt: skip
    return log_id


def rows_of(owner, dataset, **kw):
    rows, total = view.list_rows(visible_of(owner, dataset), page=kw.pop("page", 1), page_size=kw.pop("page_size", 20), keywords=kw.pop("keywords", None))
    return {r["id"]: r for r in rows}, total


def test_a_never_parsed_text_file_and_an_image_and_a_disabled_document(settings, space, storage):
    owner, dataset = space
    txt = one(settings, owner, dataset, storage)
    png = one(settings, owner, dataset, storage, "p.png", b"\x89PNG\r\n\x1a\n" + b"x" * 64)
    off = one(settings, owner, dataset, storage, "off.txt", text_bytes("off"))
    set_doc(off["id"], status="0")
    rows, total = rows_of(owner, dataset)
    assert total == 3
    assert rows[txt["id"]] == {**rows[txt["id"]], "run": "0", "progress": 0.0, "progress_message": "", "chunk_count": 0, "parseable": True, "enabled": True,
                               "thumbnail": None, "last_log_id": None, "pages_total": None, "pages_without_text": None, "error": None}  # fmt: skip
    assert rows[png["id"]]["parseable"] is False
    assert rows[off["id"]]["enabled"] is False
    assert set(rows[txt["id"]]) == set(view.ROW_KEYS)


def test_the_row_keys_hide_storage_and_internal_columns():
    assert not {"location", "status", "source", "content_hash", "source_type", "progress_msg"} & set(view.ROW_KEYS)
    assert "created_by" in view.ROW_KEYS and "enabled" in view.ROW_KEYS


def test_a_finished_pdf_reports_its_page_counts_from_the_newest_log(settings, space, storage):
    owner, dataset = space
    doc = one(settings, owner, dataset, storage, "f.pdf", thirteen_page_pdf())
    set_doc(doc["id"], run="3", progress=1.0, chunk_num=7, token_num=70)
    add_log(owner, dataset, doc, status="done", dsl={"pages_total": 1, "pages_without_text": 0}, create_time=1_000)
    newest = add_log(owner, dataset, doc, status="done", dsl={"pages_total": 13, "pages_without_text": 2}, create_time=2_000)
    row = rows_of(owner, dataset)[0][doc["id"]]
    assert (row["pages_total"], row["pages_without_text"], row["last_log_id"]) == (13, 2, newest)
    assert (row["run"], row["chunk_count"], row["token_num"], row["error"]) == ("3", 7, 70, None)


def test_a_failed_document_carries_a_typed_error_and_its_last_line(settings, space, storage):
    owner, dataset = space
    doc = one(settings, owner, dataset, storage)
    set_doc(doc["id"], run="4", progress=-1.0, progress_msg="first line\n[failed] step=parse code=file_damaged message=The file could not be read.")
    add_log(owner, dataset, doc, status="failed", dsl={"error": {"step": "parse", "code": "file_damaged", "message": "The file could not be read.", "detail": "secret path /x"}})
    row = rows_of(owner, dataset)[0][doc["id"]]
    assert row["error"] == {"step": "parse", "code": "file_damaged", "message": row["error"]["message"]}
    assert row["error"]["message"] and "secret" not in row["error"]["message"]
    assert row["progress_message"].startswith("[failed] step=parse")
    assert "first line" not in row["progress_message"]


def test_a_cancelled_document_has_no_error(settings, space, storage):
    owner, dataset = space
    doc = one(settings, owner, dataset, storage)
    set_doc(doc["id"], run="2", chunk_num=3)
    add_log(owner, dataset, doc, status="cancelled")
    row = rows_of(owner, dataset)[0][doc["id"]]
    assert row["error"] is None and row["run"] == "2" and row["chunk_count"] == 3


@pytest.mark.parametrize(
    ("value", "shown"),
    [
        (JPEG, True),
        (PNG_URL, True),
        ("data:image/svg+xml;base64,PHN2Zz4=", False),
        ("javascript:alert(1)", False),
        ("<img src=x onerror=alert(1)>", False),
        (JPEG + "A" * 20000, False),
        ("", False),
    ],
)
def test_only_small_jpeg_and_png_data_urls_are_returned_as_thumbnails(settings, space, storage, value, shown):
    owner, dataset = space
    doc = one(settings, owner, dataset, storage)
    set_doc(doc["id"], thumbnail=value)
    assert rows_of(owner, dataset)[0][doc["id"]]["thumbnail"] == (value if shown else None)


def test_a_running_message_is_the_last_line_cut_redacted_and_only_running_rows_ask(settings, space, storage, monkeypatch):
    owner, dataset = space
    running = one(settings, owner, dataset, storage)
    idle = one(settings, owner, dataset, storage, "idle.txt", text_bytes("idle"))
    long_line = "x" * 900
    set_doc(running["id"], run="1", progress=0.4, progress_msg=f"early\n{long_line}\n\n")
    set_doc(idle["id"], run="0", progress_msg="old message")
    rows = rows_of(owner, dataset)[0]
    assert rows[running["id"]]["progress_message"] == "x" * 300
    assert rows[idle["id"]]["progress_message"] == ""
    set_doc(running["id"], progress_msg="calling https://user:hunter2@host.example/v1 now")
    assert "hunter2" not in rows_of(owner, dataset)[0][running["id"]]["progress_message"]


def test_a_page_of_twenty_rows_costs_at_most_four_statements_and_no_doc_store_call(settings, space, storage, monkeypatch):
    owner, dataset = space
    docs = [one(settings, owner, dataset, storage, f"d{i}.txt", text_bytes(f"d{i}")) for i in range(20)]
    for i, doc in enumerate(docs):
        if i % 2:
            set_doc(doc["id"], run="1", progress_msg="line a\nline b")
        add_log(owner, dataset, doc, status="running")
    seen: list[str] = []
    real = DB.obj.execute_sql

    def counting(sql_text, params=None, *a, **k):
        seen.append(sql_text)
        return real(sql_text, params, *a, **k)

    def forbidden(*args, **kwargs):
        raise AssertionError("the list must not call the document store")

    monkeypatch.setattr(DB.obj, "execute_sql", counting)
    monkeypatch.setattr("rag.utils.es_conn.get_doc_store", forbidden)
    rows, total = view.list_rows(visible_of(owner, dataset), page=1, page_size=20, keywords=None)
    assert len(rows) == 20 and total == 20
    selects = [s for s in seen if s.lstrip().upper().startswith("SELECT")]
    assert len(selects) <= 4, selects


def test_paging_search_and_escaping_follow_the_phase_three_list(settings, space, storage):
    owner, dataset = space
    for name in ("a_1.txt", "aX1.txt", "b.txt"):
        one(settings, owner, dataset, storage, name, text_bytes(name))
    rows, total = rows_of(owner, dataset, keywords="a_1")
    assert total == 1 and next(iter(rows.values()))["name"] == "a_1.txt"
    rows, total = rows_of(owner, dataset, page=2, page_size=2)
    assert total == 3 and len(rows) == 1
    assert refused(lambda: view.list_rows(visible_of(owner, dataset), page=1, page_size=5, keywords="k" * 129)).kind is Kind.INVALID


def test_detail_has_the_row_facts_and_the_chunking_settings(settings, space, storage):
    owner, dataset = space
    doc = upload(settings, owner, dataset, [item("c.txt", text_bytes("c"))], storage=storage, parser_config={"chunk_token_num": 256, "delimiter": "##", "overlapped_percent": 10})[0]
    detail = view.document_detail(settings, visible_of(owner, dataset), doc["id"], storage=storage)
    assert detail["parser_id"] == "naive" and detail["chunk_token_num"] == 256 and detail["delimiter"] == "##" and detail["overlapped_percent"] == 10
    assert detail["preview"] == "none" and detail["pages_total"] is None and detail["suffix"] == "txt" and detail["size"] == doc["size"]
    assert set(view.ROW_KEYS) <= set(detail)
    plain = view.document_detail(settings, visible_of(owner, dataset), one(settings, owner, dataset, storage, "n.txt", text_bytes("n"))["id"], storage=storage)
    assert plain["chunk_token_num"] == 512 and plain["overlapped_percent"] == 0 and plain["delimiter"]


def test_detail_of_a_pdf_reads_the_page_count_once_and_a_foreign_id_is_not_found(settings, space, storage):
    owner, dataset = space
    doc = one(settings, owner, dataset, storage, "p.pdf", thirteen_page_pdf())
    detail = view.document_detail(settings, visible_of(owner, dataset), doc["id"], storage=storage)
    assert detail["preview"] == "pages" and detail["pages_total"] == 13
    err = refused(lambda: view.document_detail(settings, visible_of(owner, dataset), uuid.uuid4().hex, storage=storage))
    assert err.kind is Kind.NOT_FOUND
    damaged = one(settings, owner, dataset, storage, "bad.pdf", b"%PDF-1.4\n" + garbage_bytes())
    assert view.document_detail(settings, visible_of(owner, dataset), damaged["id"], storage=storage)["preview"] == "none"


class CountingStorage:
    def __init__(self, inner: Storage) -> None:
        self.inner = inner
        self.reads = 0

    def iter_chunks(self, bucket, key, chunk_size=1 << 20):
        self.reads += 1
        return self.inner.iter_chunks(bucket, key, chunk_size)


def test_the_page_count_is_cached_per_document_and_hash(settings, space, storage):
    owner, dataset = space
    doc = one(settings, owner, dataset, storage, "q.pdf", thirteen_page_pdf())
    row = sql("SELECT `location`, `content_hash` FROM `document` WHERE `id` = %s", (doc["id"],))[0]
    counting = CountingStorage(storage)
    pdf_pages.clear_cache()
    first = pdf_pages.pdf_page_count(settings, doc["id"], row[0], row[1], "pdf", storage=counting)
    second = pdf_pages.pdf_page_count(settings, doc["id"], row[0], row[1], "pdf", storage=counting)
    assert first == second == 13 and counting.reads == 1
    assert pdf_pages.pdf_page_count(settings, doc["id"], row[0], "otherhash", "pdf", storage=counting) == 13 and counting.reads == 2
    assert pdf_pages.pdf_page_count(settings, doc["id"], row[0], row[1], "txt", storage=counting) is None and counting.reads == 2


def test_a_damaged_pdf_has_no_page_count(settings, space, storage):
    owner, dataset = space
    doc = one(settings, owner, dataset, storage, "d.pdf", b"%PDF-1.4\n" + garbage_bytes())
    row = sql("SELECT `location`, `content_hash` FROM `document` WHERE `id` = %s", (doc["id"],))[0]
    pdf_pages.clear_cache()
    assert pdf_pages.pdf_page_count(settings, doc["id"], row[0], row[1], "pdf", storage=storage) is None
