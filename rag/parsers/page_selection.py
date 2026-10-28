"""Pure one-based inclusive selection to merged zero-based task intervals."""

from collections.abc import Sequence


def selected_ranges(pages: Sequence[Sequence[int]] | None, bounds: tuple[int, int]) -> list[tuple[int, int]]:
    first, last = bounds
    if not pages:
        return [bounds]
    ranges = sorted((max(first, start - 1), min(last, end)) for start, end in pages)
    result = []
    for start, end in ranges:
        if start >= end:
            continue
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(end, result[-1][1]))
        else:
            result.append((start, end))
    return result
