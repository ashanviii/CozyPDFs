"""Table detection and reconstruction.

Detection is delegated entirely to PyMuPDF's own `find_tables()` — a
reliable, already-available capability, not something worth reimplementing.
What this module adds is the confidence gate PyMuPDF doesn't provide: a
found table is only reconstructed as a semantic HTML table when its
extracted grid is regular (consistent column count, mostly-filled cells);
anything ragged or sparse — the signature of a merged-cell or otherwise
irregular table `find_tables()` can locate but not cleanly extract — is
preserved as a cropped image instead. A garbled `<table>` is worse than a
picture of one.
"""

import logging

import pymupdf

from cozypdfs.conversion.render import crop_to_png
from cozypdfs.conversion.types import BBox, PreBlock, TableRegion
from cozypdfs.dir.schema import BlockType

logger = logging.getLogger("cozypdfs.conversion.tables")

_HIGH_CONFIDENCE = 0.9
_LOW_CONFIDENCE = 0.3
_MIN_ROWS = 2
_MIN_COLS = 2
_MIN_CONSISTENCY = 0.9
_MIN_FILL_RATIO = 0.6


def detect_tables(doc: pymupdf.Document) -> list[TableRegion]:
    regions: list[TableRegion] = []
    for index in range(doc.page_count):
        page = doc[index]
        try:
            found = page.find_tables()
        except Exception:
            logger.warning("find_tables failed on page %d", index + 1, exc_info=True)
            continue
        for table in found.tables:
            try:
                rows = [[cell or "" for cell in row] for row in table.extract()]
            except Exception:  # noqa: BLE001
                rows = []
            regions.append(
                TableRegion(
                    bbox=BBox(*table.bbox),
                    page_number=index + 1,
                    rows=rows,
                    confidence=_table_confidence(rows),
                )
            )
    return regions


def _table_confidence(rows: list[list[str]]) -> float:
    if len(rows) < _MIN_ROWS:
        return _LOW_CONFIDENCE
    col_counts = [len(row) for row in rows]
    max_cols = max(col_counts)
    if max_cols < _MIN_COLS:
        return _LOW_CONFIDENCE

    consistency = sum(1 for count in col_counts if count == max_cols) / len(col_counts)
    total_cells = sum(col_counts)
    filled_cells = sum(1 for row in rows for cell in row if cell.strip())
    fill_ratio = filled_cells / total_cells if total_cells else 0.0

    if consistency >= _MIN_CONSISTENCY and fill_ratio >= _MIN_FILL_RATIO:
        return _HIGH_CONFIDENCE
    return _LOW_CONFIDENCE


def build_table_block(doc: pymupdf.Document, table: TableRegion, order_hint: int) -> PreBlock:
    if table.confidence >= _HIGH_CONFIDENCE:
        return PreBlock(
            type=BlockType.TABLE.value,
            content=_rows_to_html(table.rows),
            page_number=table.page_number,
            order_hint=order_hint,
            confidence=table.confidence,
            preserve_as_image=False,
        )

    png_bytes, size = crop_to_png(doc, table.page_number, table.bbox)
    return PreBlock(
        type=BlockType.TABLE.value,
        content="",
        page_number=table.page_number,
        order_hint=order_hint,
        confidence=table.confidence,
        preserve_as_image=True,
        asset_bytes=png_bytes,
        asset_size=size,
        asset_alt="Table preserved as an image (not confidently reconstructable)",
    )


def _rows_to_html(rows: list[list[str]]) -> str:
    if not rows:
        return "<table></table>"
    header, *body = rows
    parts = ["<table><thead><tr>"]
    parts += [f"<th>{_escape(cell)}</th>" for cell in header]
    parts.append("</tr></thead>")
    if body:
        parts.append("<tbody>")
        for row in body:
            parts.append("<tr>" + "".join(f"<td>{_escape(cell)}</td>" for cell in row) + "</tr>")
        parts.append("</tbody>")
    parts.append("</table>")
    return "".join(parts)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
