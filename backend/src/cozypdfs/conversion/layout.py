"""Stage: layout analysis. Per-page PageContent -> column bands and a first
role pass over every line: is this page furniture (repeated header/footer/
page number, excluded from the reading flow) or content (kept)?

Two distinct heuristics, both deterministic and explainable:

Column detection (per page, independent of other pages): scans the actual
x-axis whitespace to find gutters — contiguous strips no candidate line's
bounding box ever crosses — and turns them into an arbitrary number of
column bands (see `_detect_columns`). This generalizes past a simple
left/right split to N columns of uneven width and uneven content, while
still falling back to one full-width band whenever the geometry is
ambiguous (a ragged mix, a diagram, ordinary single-column prose), per the
product rule that an uncertain layout must never produce interleaved
reading order.

Furniture detection (whole-document, since "repeated" is a cross-page
property): a line's text is normalized (digit runs collapsed, so "Page 42"
and "Page 43" count as the same pattern) and counted per page in the
top/bottom margin bands. A pattern repeating across roughly half the pages
is furniture; anything else in the bottom band that looks like it (smaller
font than body, or opens with a footnote-style marker) is kept as a
footnote — the two are deliberately distinguished so a footnote is never
deleted just for being physically near the bottom of a page.
"""

import math
import re
from collections import defaultdict
from statistics import mode

from cozypdfs.conversion.geometry import inside_any
from cozypdfs.conversion.types import (
    ClassifiedLine,
    ColumnBand,
    LayoutResult,
    Line,
    LineRole,
    PageContent,
    PageLayout,
    TableRegion,
)

_TOP_BAND_FRACTION = 0.08
_BOTTOM_BAND_FRACTION = 0.10
_MIN_GUTTER_PT = 8.0
_COLUMN_CANDIDATE_MAX_WIDTH_FRACTION = 0.6
_MIN_COLUMN_CANDIDATES = 4
_FOOTNOTE_SIZE_RATIO = 0.9
_FOOTNOTE_MARKER_RE = re.compile(r"^\s*(\*|†|‡|\d{1,2}|\[\d{1,2}\])[\s.)]")
_DIGIT_RUN_RE = re.compile(r"\d+")


def analyze_layout(pages: list[PageContent], tables: list[TableRegion] | None = None) -> LayoutResult:
    tables_by_page: dict[int, list[TableRegion]] = defaultdict(list)
    for table in tables or []:
        tables_by_page[table.page_number].append(table)

    dominant_body_size = _dominant_body_size(pages, tables_by_page)
    furniture = _detect_furniture(pages)
    decorative_xrefs = _detect_decorative_images(pages)

    laid_out_pages = [
        _layout_page(page, furniture, dominant_body_size, decorative_xrefs, tables_by_page[page.page_number])
        for page in pages
    ]
    return LayoutResult(pages=laid_out_pages, dominant_body_size=dominant_body_size)


def _detect_decorative_images(pages: list[PageContent]) -> set[int]:
    """An image (by PyMuPDF xref identity) that recurs across roughly half
    the document's pages is a logo/watermark, not real content — the same
    "repeated across pages" signal layout.py already uses for text
    furniture, applied to images."""
    counts: dict[int, int] = defaultdict(int)
    for page in pages:
        for image in page.images:
            if image.xref >= 0:
                counts[image.xref] += 1
    min_repeats = max(3, math.ceil(len(pages) * 0.5))
    return {xref for xref, count in counts.items() if count >= min_repeats}


def _dominant_body_size(pages: list[PageContent], tables_by_page: dict[int, list[TableRegion]]) -> float:
    """The mode of line sizes, excluding the top/bottom margin bands and
    any line inside a detected table. Headers/footers/page-numbers are
    very often set in a different (and itself repeated) size, and table
    cells are very often set smaller than body prose — with a small page
    count either can tie with or outnumber the true body size, which
    would corrupt every downstream heading/equation decision. Body text
    essentially never lives in either place, so excluding them is safe."""
    sizes = [
        round(line.size, 1)
        for page in pages
        for line in page.lines
        if line.text.strip()
        and page.height * _TOP_BAND_FRACTION < line.bbox.y0
        and line.bbox.y1 < page.height * (1 - _BOTTOM_BAND_FRACTION)
        and not inside_any(line.bbox, [t.bbox for t in tables_by_page.get(page.page_number, [])])
    ]
    if not sizes:
        return 10.0
    return mode(sizes)


def _normalize(text: str) -> str:
    return _DIGIT_RUN_RE.sub("#", text.strip().lower())


def _detect_furniture(pages: list[PageContent]) -> dict[str, LineRole]:
    top_counts: dict[str, int] = defaultdict(int)
    bottom_counts: dict[str, int] = defaultdict(int)

    for page in pages:
        top_cutoff = page.height * _TOP_BAND_FRACTION
        bottom_cutoff = page.height * (1 - _BOTTOM_BAND_FRACTION)
        seen_top: set[str] = set()
        seen_bottom: set[str] = set()
        for line in page.lines:
            key = _normalize(line.text)
            if not key:
                continue
            if line.bbox.y1 <= top_cutoff:
                seen_top.add(key)
            elif line.bbox.y0 >= bottom_cutoff:
                seen_bottom.add(key)
        for key in seen_top:
            top_counts[key] += 1
        for key in seen_bottom:
            bottom_counts[key] += 1

    min_repeats = max(3, math.ceil(len(pages) * 0.5))
    roles: dict[str, LineRole] = {}
    for key, count in top_counts.items():
        if count >= min_repeats:
            roles[key] = LineRole.HEADER
    for key, count in bottom_counts.items():
        if count >= min_repeats and key not in roles:
            roles[key] = LineRole.PAGE_NUMBER if re.fullmatch(r"[#\-\s]+", key) else LineRole.FOOTER
    return roles


def _layout_page(
    page: PageContent,
    furniture: dict[str, LineRole],
    dominant_body_size: float,
    decorative_xrefs: set[int],
    tables: list[TableRegion],
) -> PageLayout:
    table_bboxes = [table.bbox for table in tables]
    column_candidates = [line for line in page.lines if not inside_any(line.bbox, table_bboxes)]
    columns = _detect_columns(column_candidates, page.width)
    top_cutoff = page.height * _TOP_BAND_FRACTION
    bottom_cutoff = page.height * (1 - _BOTTOM_BAND_FRACTION)

    classified: list[ClassifiedLine] = []
    for line in page.lines:
        role = _classify_furniture_or_body(
            line, furniture, top_cutoff, bottom_cutoff, dominant_body_size
        )
        classified.append(ClassifiedLine(line=line, role=role))

    images = [image for image in page.images if image.xref not in decorative_xrefs]

    return PageLayout(
        page_number=page.page_number,
        width=page.width,
        height=page.height,
        columns=columns,
        classified_lines=classified,
        images=images,
    )


def _classify_furniture_or_body(
    line: Line,
    furniture: dict[str, LineRole],
    top_cutoff: float,
    bottom_cutoff: float,
    dominant_body_size: float,
) -> LineRole:
    key = _normalize(line.text)
    furniture_role = furniture.get(key)

    in_top_band = line.bbox.y1 <= top_cutoff
    in_bottom_band = line.bbox.y0 >= bottom_cutoff

    if furniture_role is not None and (in_top_band or in_bottom_band):
        return furniture_role

    if in_bottom_band and _looks_like_footnote(line, dominant_body_size):
        return LineRole.FOOTNOTE

    return LineRole.BODY


def _looks_like_footnote(line: Line, dominant_body_size: float) -> bool:
    text = line.text.strip()
    if not text:
        return False
    smaller_font = line.size <= dominant_body_size * _FOOTNOTE_SIZE_RATIO
    has_marker = bool(_FOOTNOTE_MARKER_RE.match(text))
    return smaller_font or has_marker


_GUTTER_BUCKET_PT = 2.0
_MAX_PLAUSIBLE_COLUMNS = 6
_MIN_BAND_COVERAGE_RATIO = 0.8
_MAX_COLUMN_SPAN_RATIO = 1.6


def _detect_columns(lines: list[Line], page_width: float) -> list[ColumnBand]:
    """Geometry-based, arbitrary-N column detection.

    A "column-width" line (see the width filter below) contributes its
    full [x0, x1] span to an x-axis coverage histogram. Any x position no
    candidate line ever covers, for a wide enough contiguous run, is a
    real whitespace gutter — this is what generalizes past a binary
    left/right split: N columns just produce N-1 such gutters, uneven
    column widths and uneven per-column content don't matter because the
    gutters are found from actual geometry, not an assumed split point.

    Full-width lines are excluded from the histogram by the coarse width
    filter below. A narrower but still gutter-bridging line — typically a
    section heading a little wider than any one column, without being
    wide enough to trip that filter — is handled separately: any line
    that is the *sole* coverage across an otherwise-empty run wide enough
    to be a gutter is identified directly (`_find_bridging_lines`) and
    excluded, rather than guessing from width statistics alone, which
    risks excluding a column's own legitimately wide content instead.

    Every candidate band is still required to pass the same safety checks
    the old binary version had (real content on both/all sides, a tight
    x-range per band, a minimum gutter width) — ambiguous geometry still
    falls back to one full-width band rather than guessing.
    """
    full_width_band = [ColumnBand(0.0, page_width)]

    candidates = [ln for ln in lines if ln.bbox.width < _COLUMN_CANDIDATE_MAX_WIDTH_FRACTION * page_width]
    if len(candidates) < _MIN_COLUMN_CANDIDATES:
        return full_width_band

    bridging_ids = _find_bridging_lines(candidates)
    candidates = [ln for ln in candidates if id(ln) not in bridging_ids]
    if len(candidates) < _MIN_COLUMN_CANDIDATES:
        return full_width_band

    content_x0 = min(ln.bbox.x0 for ln in candidates)
    content_x1 = max(ln.bbox.x1 for ln in candidates)
    gutters = _find_gutters(candidates, content_x0, content_x1)
    if not gutters:
        return full_width_band

    bands = _bands_from_gutters(content_x0, content_x1, gutters)
    if len(bands) < 2 or len(bands) > _MAX_PLAUSIBLE_COLUMNS:
        return full_width_band

    assigned_per_band = _assign_candidates(candidates, bands)
    if not _bands_are_plausible(candidates, assigned_per_band):
        return full_width_band

    return bands


def _find_gutters(candidates: list[Line], content_x0: float, content_x1: float) -> list[tuple[float, float]]:
    n_buckets = int((content_x1 - content_x0) / _GUTTER_BUCKET_PT) + 2
    coverage = [0] * n_buckets

    def bucket_of(x: float) -> int:
        return min(max(int((x - content_x0) / _GUTTER_BUCKET_PT), 0), n_buckets - 1)

    for ln in candidates:
        for b in range(bucket_of(ln.bbox.x0), bucket_of(ln.bbox.x1) + 1):
            coverage[b] += 1

    # Strictly zero coverage, deliberately: a column's own single widest
    # line naturally creates a low-but-nonzero tail past where its
    # shorter siblings end, and that must never be mistaken for a gutter.
    # What made a title/caption spanning a real gutter a problem earlier
    # is handled separately, by excluding such width outliers from
    # `candidates` before this function ever runs (see
    # `_exclude_width_outliers`) — not by loosening what counts as clear
    # whitespace here.
    gutters: list[tuple[float, float]] = []
    run_start: int | None = None
    for i, count in enumerate(coverage):
        if count == 0:
            if run_start is None:
                run_start = i
        elif run_start is not None:
            _maybe_add_gutter(gutters, run_start, i, content_x0)
            run_start = None
    if run_start is not None:
        _maybe_add_gutter(gutters, run_start, n_buckets, content_x0)

    # Interior gutters only — a leading/trailing empty bucket is just page
    # margin, not a gutter between two columns.
    return [g for g in gutters if g[0] > content_x0 + 1 and g[1] < content_x1 - 1]


def _maybe_add_gutter(gutters: list[tuple[float, float]], start: int, end: int, content_x0: float) -> None:
    x0 = content_x0 + start * _GUTTER_BUCKET_PT
    x1 = content_x0 + end * _GUTTER_BUCKET_PT
    if x1 - x0 >= _MIN_GUTTER_PT:
        gutters.append((x0, x1))


def _bands_from_gutters(
    content_x0: float, content_x1: float, gutters: list[tuple[float, float]]
) -> list[ColumnBand]:
    edges = [content_x0]
    for g0, g1 in gutters:
        edges.append(g0)
        edges.append(g1)
    edges.append(content_x1)
    return [ColumnBand(edges[i], edges[i + 1]) for i in range(0, len(edges), 2)]


def _assign_candidates(candidates: list[Line], bands: list[ColumnBand]) -> list[list[Line]]:
    per_band: list[list[Line]] = [[] for _ in bands]
    tolerance = 3.0
    for ln in candidates:
        for i, band in enumerate(bands):
            if ln.bbox.x0 >= band.x0 - tolerance and ln.bbox.x1 <= band.x1 + tolerance:
                per_band[i].append(ln)
                break
    return per_band


def _bands_are_plausible(candidates: list[Line], per_band: list[list[Line]]) -> bool:
    if any(not lines for lines in per_band):
        # A band nothing was assigned to means the gutter geometry doesn't
        # actually correspond to real column content — likely noise.
        return False
    assigned = sum(len(lines) for lines in per_band)
    if assigned / len(candidates) < _MIN_BAND_COVERAGE_RATIO:
        return False
    return all(_is_tight_column(lines) for lines in per_band)


def _is_tight_column(lines: list[Line]) -> bool:
    span = max(ln.bbox.x1 for ln in lines) - min(ln.bbox.x0 for ln in lines)
    typical_width = sum(ln.bbox.width for ln in lines) / len(lines)
    if typical_width <= 0:
        return True
    return span <= typical_width * _MAX_COLUMN_SPAN_RATIO


_BRIDGING_MIN_RUN_PT = 20.0


def _find_bridging_lines(candidates: list[Line]) -> set[int]:
    """Finds lines that bridge a real gutter — sit alone (coverage == 1)
    across a wide run with genuine content (coverage > 0 from *other*
    lines) immediately on both sides. That "dense | thin single-line
    bridge | dense" shape is specific to a heading/caption spanning two
    columns; it does not match a column's own widest line's trailing
    edge, which fades from dense content on one side straight into the
    real gutter's zero coverage on the other — there's nothing dense on
    that far side to require excluding it. Requiring dense content on
    *both* sides is what tells the two apart without needing to guess
    from width statistics.

    Returns `id()`s (Line isn't hashable) of the lines to exclude.
    """
    if len(candidates) < _MIN_COLUMN_CANDIDATES:
        return set()

    content_x0 = min(ln.bbox.x0 for ln in candidates)
    content_x1 = max(ln.bbox.x1 for ln in candidates)
    n_buckets = int((content_x1 - content_x0) / _GUTTER_BUCKET_PT) + 2

    def bucket_of(x: float) -> int:
        return min(max(int((x - content_x0) / _GUTTER_BUCKET_PT), 0), n_buckets - 1)

    coverage = [0] * n_buckets
    sole_owner: list[int | None] = [None] * n_buckets
    for ln in candidates:
        for b in range(bucket_of(ln.bbox.x0), bucket_of(ln.bbox.x1) + 1):
            coverage[b] += 1
    for ln in candidates:
        for b in range(bucket_of(ln.bbox.x0), bucket_of(ln.bbox.x1) + 1):
            if coverage[b] == 1:
                sole_owner[b] = id(ln)

    bridging: set[int] = set()
    run_start: int | None = None
    run_owner: int | None = None
    for i in range(n_buckets + 1):
        owner_here = sole_owner[i] if i < n_buckets else None
        if owner_here is not None and (run_start is None or owner_here == run_owner):
            if run_start is None:
                run_start = i
                run_owner = owner_here
            continue

        if run_start is not None:
            width = (i - run_start) * _GUTTER_BUCKET_PT
            left_dense = run_start > 0 and coverage[run_start - 1] > 0
            right_dense = i < n_buckets and coverage[i] > 0
            if width >= _BRIDGING_MIN_RUN_PT and left_dense and right_dense:
                bridging.add(run_owner)

        run_start = i if owner_here is not None else None
        run_owner = owner_here

    return bridging
