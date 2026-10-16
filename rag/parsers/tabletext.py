"""Shared helper: render rows as escaped HTML table text for DOCX, XLSX and PPTX blocks."""

from __future__ import annotations

import html
from collections.abc import Iterable, Sequence


def render_table(rows: Iterable[Sequence[object]]) -> str:
    out = ["<table>"]
    for row in rows:
        cells = "".join(f"<td>{html.escape('' if c is None else str(c))}</td>" for c in row)
        out.append(f"<tr>{cells}</tr>")
    out.append("</table>")
    return "\n".join(out)
