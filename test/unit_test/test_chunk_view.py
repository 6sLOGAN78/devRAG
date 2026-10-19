"""The shared shaping of positions and page sizes for chunk views (plan 05-04; moved out of the chunk service unchanged)."""

from __future__ import annotations

from api.db.services.chunk_view import chunk_view_fields, merge_page_sizes, page_sizes_of, positions_of


def test_nested_position_int_becomes_boxes():
    row = {"position_int": [[1, 10, 20, 30, 40], [2, 11, 21, 31, 41]]}
    assert positions_of(row) == [
        {"page": 1, "x0": 10, "top": 20, "x1": 30, "bottom": 40},
        {"page": 2, "x0": 11, "top": 21, "x1": 31, "bottom": 41},
    ]


def test_flat_position_int_is_read_with_stride_five():
    row = {"position_int": [1, 10, 20, 30, 40, 3, 1, 2, 3, 4]}
    assert [p["page"] for p in positions_of(row)] == [1, 3]


def test_a_short_or_missing_position_list_gives_no_boxes():
    assert positions_of({}) == []
    assert positions_of({"position_int": None}) == []
    assert positions_of({"position_int": [1, 2, 3]}) == []
    assert positions_of({"position_int": [[1, 2, 3]]}) == []


def test_page_sizes_of_a_row_keeps_the_pages_its_boxes_use():
    row = {"position_int": [[2, 0, 0, 1, 1]], "page_dims_flt": [[1, 600.0, 800.0], [2, 612.0, 792.0]]}
    assert page_sizes_of(row) == {"2": [612.0, 792.0]}


def test_page_sizes_of_a_row_can_be_asked_for_wanted_pages():
    row = {"page_dims_flt": [[1, 600.0, 800.0], [2, 612.0, 792.0]]}
    assert page_sizes_of(row, {1}) == {"1": [600.0, 800.0]}


def test_malformed_page_dims_are_skipped():
    row = {"position_int": [[1, 0, 0, 1, 1]], "page_dims_flt": [[1, 600.0], "x", None, [1, 600.0, 800.0]]}
    assert page_sizes_of(row) == {"1": [600.0, 800.0]}


def test_merge_sorts_pages_numerically():
    merged = merge_page_sizes([{"10": [1.0, 2.0]}, {"2": [3.0, 4.0]}])
    assert list(merged) == ["2", "10"]


def test_chunk_view_fields_holds_positions_and_page_sizes():
    row = {"position_int": [[1, 1, 2, 3, 4]], "page_dims_flt": [[1, 612.0, 792.0]]}
    assert chunk_view_fields(row) == {
        "positions": [{"page": 1, "x0": 1, "top": 2, "x1": 3, "bottom": 4}],
        "page_sizes": {"1": [612.0, 792.0]},
    }
