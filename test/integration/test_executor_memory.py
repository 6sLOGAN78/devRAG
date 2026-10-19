"""Peak memory of the real task-executor container while it parses the phase's test documents (plan 04-35, D-29).

The documents go through the real route, queue, executor container and index; only the third-party provider is the
loopback fake. The peak is the larger of the highest ``docker stats`` sample and the container cgroup's own
``memory.peak`` high-water mark (page cache included, so it is conservative). The container limit must be at least 1/0.6 of the peak.
"""
from __future__ import annotations

import re
import threading
from collections.abc import Iterator

import httpx
import pytest

from scripts.record_memory import to_mib
from test.helpers.accounts import AccountRegistry, unique_name
from test.helpers.fake_provider import FakeProvider, fake_provider_stack  # noqa: F401  (fixture)
from test.helpers.ingest import build_format_files, marker_word, paragraphs, start_parse, upload_text, wait_run
from test.helpers.pdf_files import thirteen_page_pdf
from test.integration.test_executor_container import DOCKER, SERVICE, _ids, _inspect, _run
from test.testcases.conftest import ingress, stack_ready  # noqa: F401  (fixtures)
from test.testcases.test_dataset_flow import DATASETS, create, workspace
from test.testcases.test_provider_flow import api, ok, registry  # noqa: F401  (registry is a fixture)

pytestmark = [pytest.mark.integration, pytest.mark.serial]

PDF = "application/pdf"
PEAK_SHARE = 0.6


class Sampler:
    """Samples the executor container's memory in a background thread until stopped."""

    def __init__(self, container: str) -> None:
        self.container = container
        self.peak = 0.0
        self.samples = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def _loop(self) -> None:
        while not self._stop.is_set():
            out = _run([DOCKER, "stats", "--no-stream", "--format", "{{.MemUsage}}", self.container], timeout=30).stdout
            if out.strip():
                self.peak = max(self.peak, to_mib(out.split("/")[0]))
                self.samples += 1

    def __enter__(self) -> "Sampler":
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join(timeout=60)


def _limit_mib(cid: str) -> float:
    return int(_inspect(cid, "{{.HostConfig.Memory}}") or 0) / 1048576


def _cgroup_peak_mib(cid: str) -> float | None:
    out = _run([DOCKER, "exec", cid, "cat", "/sys/fs/cgroup/memory.peak"]).stdout.strip()
    return int(out) / 1048576 if re.fullmatch(r"\d+", out) else None


@pytest.fixture
def owner_and_dataset(stack_ready: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> Iterator[tuple[httpx.Client, object, str]]:  # noqa: F811
    owner = workspace(stack_ready, registry, fake_provider_stack, "mem")
    dataset = ok(create(stack_ready, owner, unique_name("Executor memory")))
    yield stack_ready, owner, str(dataset["id"])


def test_the_executor_stays_under_its_limit_while_parsing_the_phase_documents(owner_and_dataset: tuple[httpx.Client, object, str]) -> None:
    ingress, owner, dataset_id = owner_and_dataset
    cid = _ids()[0]
    limit = _limit_mib(cid)
    assert limit > 0, "the executor has a memory limit"

    files: dict[str, tuple[bytes, str]] = {"thirteen.pdf": (thirteen_page_pdf(), PDF), "forty.txt": (paragraphs(40), "text/plain")}
    for suffix, (name, data, _fragments) in build_format_files(marker_word("mem")).items():
        if suffix in (".docx", ".xlsx", ".pptx", ".html"):
            files[name] = (data, "application/octet-stream")
    docs: list[str] = []
    for name, (data, mime) in files.items():
        doc = upload_text(ingress, owner, dataset_id, data, name, mime=mime)
        ok(api(ingress, "PATCH", f"{DATASETS}/{dataset_id}/documents/{doc['id']}", owner.token, body={"parser_config": {"chunk_token_num": 25 if name.endswith(".pdf") else 128}}))  # type: ignore[attr-defined]
        docs.append(str(doc["id"]))

    with Sampler(cid) as sampler:
        for doc_id in docs:  # one after another
            assert start_parse(ingress, owner, dataset_id, [doc_id]).status_code == 200
            wait_run(ingress, owner, dataset_id, doc_id, "3", timeout=180)
        for pair in (docs[:2], docs[2:4], docs[4:6]):  # then two at once
            assert start_parse(ingress, owner, dataset_id, pair, confirm=True).status_code == 200
            for doc_id in pair:
                wait_run(ingress, owner, dataset_id, doc_id, "3", timeout=180)

    cgroup_peak = _cgroup_peak_mib(cid)
    # The sampler is coarse (a `docker stats` call takes about two seconds), so the cgroup high-water mark, when readable, counts too.
    peak = max(sampler.peak, cgroup_peak or 0.0)
    print(f"EXECUTOR_PEAK_MIB={peak:.1f} sampled_mib={sampler.peak:.1f} samples={sampler.samples} limit_mib={limit:.0f} cgroup_peak_mib={cgroup_peak}")
    assert sampler.samples >= 5, "the sampler saw the run"
    assert _inspect(cid, "{{.State.OOMKilled}}") == "false"
    assert peak < limit
    assert peak <= PEAK_SHARE * limit, f"peak {peak:.0f} MiB is above {PEAK_SHARE:.0%} of the {limit:.0f} MiB limit"
