"""Stage 2: layout analysis.

Classifies each raw block by role -- body text, heading candidate, header,
footer, page number, or image -- and groups blocks into columns per page.

Nothing here decides "this is chapter 3" or "this is a paragraph about the
weather." It only answers narrower, purely positional/typographic
questions: is this block in the header strip? Is its font conspicuously
larger than the body text? Is the page laid out in columns? Those signals
are consumed by later stages (artifact removal, chapter detection) that
have document-wide context.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter

from ..models import (
    DocumentStats,
    LayoutRegion,
    PageLayout,
    RawBlock,
    RawBlockType,
    RawDocument,
    RegionType,
)

# Top/bottom slice of the page treated as the running-header/footer zone.
_HEADER_ZONE_FRACTION = 0.10
_FOOTER_ZONE_FRACTION = 0.10

# A heading candidate must be short and noticeably larger/bolder than body text.
_HEADING_MAX_LINES = 2
_HEADING_MAX_CHARS = 120
_HEADING_SIZE_RATIO = 1.15
_HEADING_BOLD_SIZE_RATIO = 1.0
_HEADING_BOLD_FRACTION = 0.8

# A block narrower than this fraction of the page can participate in column
# clustering; wider blocks are treated as full-width (headings, images).
_FULL_WIDTH_FRACTION = 0.6
_MIN_COLUMN_CANDIDATES = 4

# A footnote candidate: noticeably smaller than body text, sitting in the
# lower part of the page but outside the strict running-footer strip
# already claimed by header/footer/page-number classification above.
_FOOTNOTE_LOWER_ZONE_FRACTION = 0.25
_FOOTNOTE_SIZE_RATIO = 0.85

_ROMAN_NUMERAL_RE = re.compile(r"^[ivxlcdm]+$", re.IGNORECASE)
_PAGE_NUMBER_STRIP_RE = re.compile(r"^[\-\s–—]*|[\-\s–—]*$")
_PAGE_PREFIX_RE = re.compile(r"^(page|p\.)\s*", re.IGNORECASE)


def compute_document_stats(doc: RawDocument) -> DocumentStats:
    """Compute the book's dominant body font size and page dimensions.

    "Large font" only means something relative to what this particular
    book uses for body text, so this must be computed before any
    heading/heading-candidate classification can happen.
    """
    char_weight: Counter[float] = Counter()
    max_size = 0.0
    for page in doc.pages:
        for block in page.blocks:
            if block.block_type != RawBlockType.TEXT:
                continue
            for line in block.lines:
                for span in line.spans:
                    n_chars = len(span.text.strip())
                    if n_chars == 0:
                        continue
                    size_bucket = round(span.font_size * 2) / 2
                    char_weight[size_bucket] += n_chars
                    max_size = max(max_size, span.font_size)

    body_size = char_weight.most_common(1)[0][0] if char_weight else 12.0
    widths = [p.width for p in doc.pages] or [612.0]
    heights = [p.height for p in doc.pages] or [792.0]
    return DocumentStats(
        body_font_size=body_size,
        max_font_size=max_size or body_size,
        page_width=statistics.median(widths),
        page_height=statistics.median(heights),
    )


class DefaultLayoutAnalyzer:
    """`LayoutAnalyzer` implementation using positional + typographic heuristics."""

    def analyze(self, doc: RawDocument, stats: DocumentStats) -> list[PageLayout]:
        return [self._analyze_page(page, stats) for page in doc.pages]

    def _analyze_page(self, page, stats: DocumentStats) -> PageLayout:
        header_zone = page.height * _HEADER_ZONE_FRACTION
        footer_zone = page.height * (1 - _FOOTER_ZONE_FRACTION)
        footnote_zone = page.height * (1 - _FOOTNOTE_LOWER_ZONE_FRACTION)

        regions: list[LayoutRegion] = []
        for block in page.blocks:
            region_type = self._classify_block(
                block, stats, header_zone, footer_zone, footnote_zone
            )
            regions.append(
                LayoutRegion(page_index=page.index, block=block, region_type=region_type)
            )

        column_count, col_map = _detect_columns(regions, page.width)
        for region in regions:
            region.column_index = col_map.get(id(region), 0)

        return PageLayout(
            page_index=page.index,
            width=page.width,
            height=page.height,
            regions=regions,
            column_count=column_count,
        )

    def _classify_block(
        self,
        block: RawBlock,
        stats: DocumentStats,
        header_zone: float,
        footer_zone: float,
        footnote_zone: float,
    ) -> RegionType:
        if block.block_type == RawBlockType.IMAGE:
            return RegionType.IMAGE

        text = _block_text(block)
        in_header = block.bbox.y1 <= header_zone
        in_footer = block.bbox.y0 >= footer_zone

        if in_header or in_footer:
            if _looks_like_page_number(text):
                return RegionType.PAGE_NUMBER
            return RegionType.HEADER if in_header else RegionType.FOOTER

        avg_size, bold_fraction = _block_font_stats(block)
        is_short = len(block.lines) <= _HEADING_MAX_LINES and len(text) <= _HEADING_MAX_CHARS
        is_large = avg_size >= stats.body_font_size * _HEADING_SIZE_RATIO
        is_bold_and_sized = (
            bold_fraction >= _HEADING_BOLD_FRACTION
            and avg_size >= stats.body_font_size * _HEADING_BOLD_SIZE_RATIO
        )
        if text and is_short and (is_large or is_bold_and_sized):
            return RegionType.HEADING_CANDIDATE

        in_lower_zone = block.bbox.y0 >= footnote_zone
        is_small = 0 < avg_size <= stats.body_font_size * _FOOTNOTE_SIZE_RATIO
        if text and in_lower_zone and is_small:
            return RegionType.FOOTNOTE

        return RegionType.BODY_TEXT


def _block_text(block: RawBlock) -> str:
    return " ".join(line.text for line in block.lines).strip()


def _block_font_stats(block: RawBlock) -> tuple[float, float]:
    """Character-weighted average font size and bold fraction for a block."""
    total_chars = 0
    size_sum = 0.0
    bold_chars = 0
    for line in block.lines:
        for span in line.spans:
            n = len(span.text)
            if n == 0:
                continue
            total_chars += n
            size_sum += span.font_size * n
            if span.bold:
                bold_chars += n
    if total_chars == 0:
        return 0.0, 0.0
    return size_sum / total_chars, bold_chars / total_chars


def _looks_like_page_number(text: str) -> bool:
    core = _PAGE_NUMBER_STRIP_RE.sub("", text)
    core = _PAGE_PREFIX_RE.sub("", core).strip()
    if not core:
        return False
    if core.isdigit() and len(core) <= 5:
        return True
    if _ROMAN_NUMERAL_RE.match(core) and len(core) <= 7:
        return True
    return False


def _detect_columns(
    regions: list[LayoutRegion], page_width: float
) -> tuple[int, dict[int, int]]:
    """Detect a genuine two-column layout, conservatively.

    Novels are single-column, and centered elements (a heading, a scene
    -break marker) or an indented paragraph's first line can easily look
    like "a different left edge" than the body margin. Left-edge
    clustering alone mistakes those for columns. So this requires actual
    side-by-side evidence: at least two blocks confidently in the left
    half and two in the right half of the page, AND blocks from each half
    actually overlapping vertically (i.e. genuinely sitting next to each
    other, not just both narrower than the page). Only body text votes --
    a heading is often centered regardless of the page's column layout.

    This deliberately only detects two columns. Truly complex (3+ column)
    layouts are out of scope for the phase-1 novel pipeline (see the
    project's staged rollout: novels first, complex layouts later).
    """
    candidates = [
        r
        for r in regions
        if r.region_type == RegionType.BODY_TEXT
        and r.block.bbox.width < page_width * _FULL_WIDTH_FRACTION
    ]
    if len(candidates) < _MIN_COLUMN_CANDIDATES:
        return 1, {}

    midpoint = page_width / 2
    left = [r for r in candidates if r.block.bbox.center_x < midpoint]
    right = [r for r in candidates if r.block.bbox.center_x >= midpoint]
    if len(left) < 2 or len(right) < 2:
        return 1, {}

    overlap_pairs = sum(
        1 for lr in left if any(_y_overlaps(lr.block.bbox, rr.block.bbox) for rr in right)
    )
    if overlap_pairs < 2:
        return 1, {}

    mapping = {id(r): 0 for r in left}
    mapping.update({id(r): 1 for r in right})
    return 2, mapping


def _y_overlaps(a, b) -> bool:
    return a.y0 < b.y1 and b.y0 < a.y1
