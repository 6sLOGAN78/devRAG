"""Page images, original bytes and text previews against the real MySQL and MinIO (plan 04-20; DOC-21, PARSE-03, UI-16, UI-19).

Storage is the real driver wrapped in a counting object; the PDF temp cache is a private instance per test. Waiting never uses a sleep.
"""

from __future__ import annotations

import io
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from PIL import Image

from api.db.services import knowledgebase_service as kbsvc
from api.db.services import page_service as pages
from api.db.services.pdf_pages import PdfFileCache
from api.db.services.service_errors import Kind, ServiceError
from common.constants import BUCKET_NAME
from rag.utils.storage_factory import get_storage
from test.helpers.accounts import AccountRegistry
from test.helpers.fake_provider import running_fake_provider
from test.helpers.ingest import World, add_document, cleanup_tasks, garbage_bytes, make_html, make_pipeline_world, text_pdf, thirteen_page_pdf
from test.helpers.uploads import sql
from test.integration.test_knowledgebase_service import principal_of
from test.integration.test_upload_service import _bound_database  # noqa: F401  (autouse module fixture)
from test.testcases.conftest import BASE_URL

pytestmark = pytest.mark.integration


@pytest.fixture
def registry() -> Iterator[AccountRegistry]:
    accounts = AccountRegistry(BASE_URL)
    try:
        yield accounts
    finally:
        cleanup_tasks(accounts)
        accounts.cleanup()


@pytest.fixture
def world(registry) -> Iterator[World]:
    with running_fake_provider() as fake:
        yield make_pipeline_world(registry, fake)


class CountingStorage:
    """The real storage with a count of full reads and a flag that says whether the last stream was closed."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.reads = 0
        self.closed = threading.Event()

    def iter_chunks(self, bucket, key, chunk_size=1 << 20):
        self.reads += 1
        self.closed.clear()
        source = self.inner.iter_chunks(bucket, key, chunk_size)
        try:
            yield from source
        finally:
            close = getattr(source, "close", None)
            if close is not None:
                close()
            self.closed.set()

    def __getattr__(self, name):
        return getattr(self.inner, name)


def visible_of(world: World):
    return kbsvc.load_visible_dataset(principal_of(world.owner), world.dataset.id)


def refused(call) -> ServiceError:
    with pytest.raises(ServiceError) as err:
        call()
    return err.value


def png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def storage() -> CountingStorage:
    from common.settings import load_settings

    return CountingStorage(get_storage(load_settings()))


@pytest.fixture
def cache() -> Iterator[PdfFileCache]:
    made = PdfFileCache()
    try:
        yield made
    finally:
        made.clear()


def test_a_page_renders_at_zoom_three_with_a_content_hash_etag(world, storage, cache):
    doc_id = add_document(world, "t.pdf", thirteen_page_pdf())
    got = pages.page_image(world.settings, visible_of(world), doc_id, 13, storage=storage, cache=cache)
    image = Image.open(io.BytesIO(got.data))
    assert image.format == "JPEG"
    assert image.size == (round(595 * 3), round(842 * 3))
    content_hash = sql("SELECT `content_hash` FROM `document` WHERE `id` = %s", (doc_id,))[0][0]
    assert content_hash in got.etag
    assert ":13:" in got.etag


def test_pages_outside_the_document_are_not_found(world, storage, cache):
    doc_id = add_document(world, "t.pdf", thirteen_page_pdf())
    for n in (0, 14, -1):
        err = refused(lambda n=n: pages.page_image(world.settings, visible_of(world), doc_id, n, storage=storage, cache=cache))
        assert err.kind is Kind.NOT_FOUND


def test_a_text_document_and_a_foreign_dataset_have_no_image(world, registry, storage, cache):
    txt = add_document(world, "t.txt", b"hello")
    assert refused(lambda: pages.page_image(world.settings, visible_of(world), txt, 1, storage=storage, cache=cache)).kind is Kind.NOT_FOUND
    pdf = add_document(world, "t.pdf", text_pdf([["x"]]))
    other = kbsvc.create_dataset(
        world.settings,
        __import__("api.db.services.tenant_scope", fromlist=["ActingScope"]).ActingScope(tenant_id=world.owner.tenant_id, role="owner", subject="owner"),
        world.owner.user_id,
        kbsvc.CreateRequest(name="other-dataset"),
    )
    visible = kbsvc.load_visible_dataset(principal_of(world.owner), other.id)
    assert refused(lambda: pages.page_image(world.settings, visible, pdf, 1, storage=storage, cache=cache)).kind is Kind.NOT_FOUND


def test_a_blank_page_renders(world, storage, cache):
    doc_id = add_document(world, "blank.pdf", text_pdf([None, None]))
    got = pages.page_image(world.settings, visible_of(world), doc_id, 2, storage=storage, cache=cache)
    assert Image.open(io.BytesIO(got.data)).size == (1785, 2526)


def test_a_damaged_pdf_is_a_typed_400_without_a_path(world, storage, cache):
    doc_id = add_document(world, "bad.pdf", b"%PDF-1.4\n" + garbage_bytes())
    err = refused(lambda: pages.page_image(world.settings, visible_of(world), doc_id, 1, storage=storage, cache=cache))
    assert err.kind is Kind.INVALID
    assert err.reason == "preview_unavailable"
    assert "/" not in err.message


def test_a_second_render_reads_storage_once(world, storage, cache):
    doc_id = add_document(world, "t.pdf", thirteen_page_pdf())
    pages.page_image(world.settings, visible_of(world), doc_id, 1, storage=storage, cache=cache)
    pages.page_image(world.settings, visible_of(world), doc_id, 2, storage=storage, cache=cache)
    assert storage.reads == 1


def test_the_cache_holds_at_most_four_files_and_evicts_from_disk(world, storage, cache):
    paths: list[Path] = []
    for i in range(5):
        doc_id = add_document(world, f"d{i}.pdf", text_pdf([[f"page {i}"]]))
        pages.page_image(world.settings, visible_of(world), doc_id, 1, storage=storage, cache=cache)
        paths.append(cache.paths()[-1])
    assert len(cache.paths()) == 4
    assert not paths[0].exists()
    assert all(p.exists() for p in paths[1:])
    assert all(len(p.stem) == 64 for p in paths)


def test_the_cache_obeys_a_byte_bound(world, storage):
    small = PdfFileCache(max_files=4, max_bytes=1)
    try:
        doc_id = add_document(world, "t.pdf", text_pdf([["x"]]))
        pages.page_image(world.settings, visible_of(world), doc_id, 1, storage=storage, cache=small)
        assert len(small.paths()) <= 1
    finally:
        small.clear()


def test_two_threads_render_different_pages_of_one_pdf(world, storage, cache):
    doc_id = add_document(world, "t.pdf", thirteen_page_pdf())
    visible = visible_of(world)

    def render(n: int) -> int:
        return len(pages.page_image(world.settings, visible, doc_id, n, storage=storage, cache=cache).data)

    with ThreadPoolExecutor(max_workers=2) as pool:
        sizes = list(pool.map(render, (1, 2)))
    assert all(size > 0 for size in sizes)


def test_the_content_stream_yields_the_exact_bytes(world, storage):
    data = (b"line of text 0123456789\n" * 4096)[:4096] * 768  # 3 MiB
    doc_id = add_document(world, "big.bin.txt", data)
    stream = pages.content_stream(world.settings, visible_of(world), doc_id, storage=storage)
    got = b"".join(stream.chunks)
    assert got == data
    assert stream.size == len(data)
    assert stream.content_type == "text/plain"
    assert stream.inline is False


def test_content_types_of_pdf_png_and_unknown(world, storage):
    pdf = add_document(world, "a.pdf", text_pdf([["x"]]))
    png = add_document(world, "a.png", png_bytes())
    docx_like = add_document(world, "a.html", make_html("<p>x</p>"))
    one = pages.content_stream(world.settings, visible_of(world), pdf, storage=storage)
    two = pages.content_stream(world.settings, visible_of(world), png, storage=storage)
    three = pages.content_stream(world.settings, visible_of(world), docx_like, storage=storage)
    try:
        assert (one.content_type, one.inline) == ("application/pdf", True)
        assert (two.content_type, two.inline) == ("image/png", True)
        assert three.content_type != "text/html"
        assert three.inline is False
    finally:
        for s in (one, two, three):
            s.close()


def test_an_early_stop_closes_the_storage_stream(world, storage):
    doc_id = add_document(world, "big.txt", b"x" * (3 << 20))
    stream = pages.content_stream(world.settings, visible_of(world), doc_id, storage=storage)
    first = next(stream.chunks)
    assert first
    stream.close()
    assert storage.closed.is_set()


def test_a_text_preview_is_cut_at_the_limit(world, storage):
    doc_id = add_document(world, "long.txt", ("a" * 300_000).encode())
    got = pages.content_text(world.settings, visible_of(world), doc_id, storage=storage)
    assert len(got["text"]) == 262144
    assert got["cut"] is True


def test_a_short_text_is_not_cut_and_gbk_decodes(world, storage):
    text = "你好，世界。这是一个中文文本预览测试。" * 5
    doc_id = add_document(world, "zh.txt", text.encode("gbk"))
    got = pages.content_text(world.settings, visible_of(world), doc_id, storage=storage)
    assert got["cut"] is False
    assert "你好" in got["text"]


def test_html_previews_as_source_text(world, storage):
    doc_id = add_document(world, "p.html", make_html("<p>hello</p>"))
    got = pages.content_text(world.settings, visible_of(world), doc_id, storage=storage)
    assert "<p>" in got["text"]


def test_pdf_and_png_have_no_text_preview(world, storage):
    for name, data in (("a.pdf", text_pdf([["x"]])), ("a.png", png_bytes())):
        doc_id = add_document(world, name, data)
        err = refused(lambda doc_id=doc_id: pages.content_text(world.settings, visible_of(world), doc_id, storage=storage))
        assert (err.kind, err.reason) == (Kind.INVALID, "preview_unavailable")


def test_safe_filename_strips_quotes_breaks_and_separators():
    got = pages.safe_filename('a"b\r\n.pdf')
    assert got and not set(got) & set('"\r\n/\\')
    assert pages.safe_filename("../../etc/passwd") == "passwd"
    assert pages.safe_filename("\r\n") != ""
    assert BUCKET_NAME
