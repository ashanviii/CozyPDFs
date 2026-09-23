"""Stage: reading-order reconstruction. Per-page layout + detected table
regions -> one flat, globally ordered sequence of content items.

This is where "PDF page = reader page" gets explicitly rejected: pages are
concatenated, never separated by a boundary marker, and within a page,
columns are resolved column-by-column — all of column 1, then all of
column 2, ... then all of column N — rather than interleaved by
y-coordinate, for however many columns layout.py detected. HEADER/FOOTER/
PAGE_NUMBER lines never reach the returned sequence — they were already
excluded by layout.py's role classification.

Lines that fall inside a detected table's bounding box are excluded from
the line stream here (the table region represents them instead) so a
table's cell text never also appears a second time as stray paragraphs.
"""

from cozypdfs.conversion.geometry import inside_any
from cozypdfs.conversion.types import (
    BBox,
    ColumnBand,
    LayoutResult,
    LineRole,
    OrderedItem,
    PageLayout,
    TableRegion,
)

_KEEP_ROLES = {LineRole.BODY, LineRole.FOOTNOTE}


def build_reading_order(layout: LayoutResult, tables: list[TableRegion]) -> list[OrderedItem]:
    tables_by_page: dict[int, list[TableRegion]] = {}
    for table in tables:
        tables_by_page.setdefault(table.page_number, []).append(table)

    ordered: list[OrderedItem] = []
    for page in layout.pages:
        ordered.extend(_order_page(page, tables_by_page.get(page.page_number, [])))
    return ordered


def _order_page(page: PageLayout, page_tables: list[TableRegion]) -> list[OrderedItem]:
    table_bboxes = [table.bbox for table in page_tables]

    content_lines = [
        cl
        for cl in page.classified_lines
        if cl.role in _KEEP_ROLES and not inside_any(cl.line.bbox, table_bboxes)
    ]
    images = [img for img in page.images if not inside_any(img.bbox, table_bboxes)]

    items: list[tuple[OrderedItem, BBox]] = [(cl, cl.line.bbox) for cl in content_lines]
    items += [(img, img.bbox) for img in images]
    items += [(table, table.bbox) for table in page_tables]

    if len(page.columns) <= 1:
        items.sort(key=lambda pair: pair[1].y0)
        return [item for item, _ in items]

    columns: list[list[tuple[OrderedItem, BBox]]] = [[] for _ in page.columns]
    spanning: list[tuple[OrderedItem, BBox]] = []
    for item, bbox in items:
        index = _column_index(bbox, page.columns)
        if index is None:
            spanning.append((item, bbox))
        else:
            columns[index].append((item, bbox))

    for column in columns:
        column.sort(key=lambda pair: pair[1].y0)
    spanning.sort(key=lambda pair: pair[1].y0)

    columns_content = [pair for column in columns for pair in column]
    columns_min_y = min((bbox.y0 for _, bbox in columns_content), default=0.0)

    # A spanning element above every column (e.g. a section heading) reads
    # first; anything else spanning (a footnote, a trailing full-width
    # figure) is safest read after all columns rather than guessing where
    # mid-flow it belongs.
    before = [pair for pair in spanning if pair[1].y1 <= columns_min_y]
    after = [pair for pair in spanning if pair[1].y1 > columns_min_y]

    ordered_pairs = before + columns_content + after
    return [item for item, _ in ordered_pairs]


def _column_index(bbox: BBox, columns: list[ColumnBand]) -> int | None:
    for index, band in enumerate(columns):
        if bbox.x0 >= band.x0 - 5 and bbox.x1 <= band.x1 + 5:
            return index
    return None
