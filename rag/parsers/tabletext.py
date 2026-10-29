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


def row_table(headers, values, caption=""):
    from rag.parsers.tables import Table, TableCell
    from rag.parsers.errors import FileTooLarge

    if len(headers) > 128:
        raise FileTooLarge()
    try:
        cells = tuple([TableCell(0, c, str(label), header=True) for c, label in enumerate(headers)] + [TableCell(1, c, "" if value is None else str(value)) for c, value in enumerate(values)])
        return Table(2, len(headers), cells, caption)
    except ValueError:
        raise FileTooLarge() from None
