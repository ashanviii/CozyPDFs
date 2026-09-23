"""Stage 3: reading-order reconstruction.

A PDF is a visual layout format: nothing guarantees blocks are stored in
the order a human would read them. This stage turns each page's
classified regions into the single linear sequence a reader would
actually follow.

For a single-column page (the common case for novels) that's simply top
to bottom. For a multi-column page, columns are detected independently
per page (see `regions.py`) rather than assumed globally, and full-width
elements (a heading spanning both columns, a full-width image) act as
anchors: everything above an anchor is read before it, everything below
after it, and between two anchors each column is read in full before
moving to the next.
"""

from __future__ import annotations

from collections import defaultdict

from ..models import LayoutRegion, PageLayout, RegionType

_FULL_WIDTH_FRACTION = 0.6


class DefaultReadingOrderResolver:
    """`ReadingOrderResolver` implementation."""

    def resolve(self, layouts: list[PageLayout]) -> list[LayoutRegion]:
        ordered: list[LayoutRegion] = []
        for page in layouts:
            ordered.extend(self._order_page(page))
        return ordered

    def _order_page(self, page: PageLayout) -> list[LayoutRegion]:
        regions = [r for r in page.regions if r.region_type != RegionType.WHITESPACE]
        if page.column_count <= 1:
            return sorted(regions, key=lambda r: (r.block.bbox.y0, r.block.bbox.x0))
        return _order_multi_column(regions, page.width)


def _order_multi_column(regions: list[LayoutRegion], page_width: float) -> list[LayoutRegion]:
    full_width = sorted(
        (r for r in regions if r.block.bbox.width >= page_width * _FULL_WIDTH_FRACTION),
        key=lambda r: r.block.bbox.y0,
    )
    full_width_ids = {id(r) for r in full_width}
    columned = [r for r in regions if id(r) not in full_width_ids]

    by_col: dict[int, list[LayoutRegion]] = defaultdict(list)
    for r in columned:
        by_col[r.column_index].append(r)
    for col in by_col.values():
        col.sort(key=lambda r: r.block.bbox.y0)
    col_indices = sorted(by_col.keys())

    # Walk the full-width anchors top to bottom. Between consecutive anchors,
    # emit every column's blocks that fall within that vertical band, one
    # column fully at a time (left to right).
    result: list[LayoutRegion] = []
    band_top = float("-inf")

    def emit_band(top: float, bottom: float) -> None:
        for col in col_indices:
            for r in by_col[col]:
                if top <= r.block.bbox.y0 < bottom:
                    result.append(r)

    for anchor in full_width:
        emit_band(band_top, anchor.block.bbox.y0)
        result.append(anchor)
        band_top = anchor.block.bbox.y0

    emit_band(band_top, float("inf"))
    return result
