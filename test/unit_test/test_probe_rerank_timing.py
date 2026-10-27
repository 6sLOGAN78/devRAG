"""Decision arithmetic for the one-off real CPU rerank timing probe."""
import pytest

from scripts.probe.time_rerank import choose_cap, choose_mem_limit, percentile

pytestmark = pytest.mark.unit


def test_percentile_interpolates_sorted_values_and_keeps_endpoints():
    assert percentile([5, 1, 3, 2, 4], 0.5) == 3
    assert percentile([5, 1, 3, 2, 4], 0.95) == pytest.approx(4.8)
    assert percentile([2], 0.95) == 2
    assert percentile([1, 2], 0) == 1
    assert percentile([1, 2], 1) == 2


@pytest.mark.parametrize("values,q", [([], 0.5), ([1], -0.1), ([1], 1.1), ([float('nan')], 0.5)])
def test_percentile_rejects_invalid_samples(values, q):
    with pytest.raises(ValueError):
        percentile(values, q)


def test_choose_cap_uses_only_the_long_chunks_and_includes_the_budget_boundary():
    rows = [
        {"n": 1024, "length": "128", "p95": 1},
        {"n": 16, "length": "512", "p95": 2},
        {"n": 32, "length": "512", "p95": 5},
        {"n": 64, "length": "512", "p95": 5.01},
    ]
    assert choose_cap(rows, budget_seconds=5) == 32
    assert choose_cap(rows) == 64  # User-approved ten-second Phase 5 budget.
    assert choose_cap(rows, budget_seconds=1) is None
    assert choose_cap([]) is None


@pytest.mark.parametrize("peak,limit", [(1, "256m"), (1024, "1280m"), (1025, "1536m"), (2048, "2560m")])
def test_memory_limit_includes_25_percent_headroom_and_rounds_up(peak, limit):
    assert choose_mem_limit(peak) == limit


def test_approved_ten_second_budget_includes_boundary_and_rejects_overrun():
    rows = [{"n": 16, "length": "512", "p95": 10}, {"n": 32, "length": "512", "p95": 10.01}]
    assert choose_cap(rows) == 16
