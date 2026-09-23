"""Stage 5: paragraph reconstruction.

PDF line breaks are not paragraph boundaries -- they are wherever the
column width happened to force a wrap. This stage walks the reading-order
line stream and decides, line by line, whether each line continues the
paragraph in progress or starts a new one, using:

* the vertical gap to the previous line, scaled to the local line height
  (a gap much bigger than a single line's height reads as a blank-line
  paragraph break)
* a left-edge indent bump relative to the body's usual flush-left margin,
  combined with the previous line ending in terminal punctuation (the
  classic "first line of a new paragraph is indented" signal)
* hyphenation at the line break (`hyphenation.py`)

Deliberately absent from that list: reaching a PDF block boundary, or
reaching a page boundary. A paragraph that runs to the bottom of one page
and resumes at the top of the next must stay one paragraph -- so crossing
a page boundary defaults to *continuing* the paragraph unless the indent +
terminal-punctuation signal says otherwise.

The output (`ParagraphCandidate`) still carries a few geometric signals
(centered, indented, font size relative to itself) forward for the
structure engine, but this is the last stage that touches raw coordinates
at all -- nothing past this point sees a bounding box.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from . import hyphenation
from .scene_breaks import looks_like_scene_break
from ..models import (
    BBox,
    DocumentStats,
    LayoutRegion,
    ParagraphCandidate,
    RawLine,
    RegionType,
    RoughKind,
    Run,
)

_TERMINAL_CHARS = set('.!?"”’)…—')
_QUOTE_START_CHARS = set('"\'“‘—')

_GAP_LINE_HEIGHT_RATIO = 1.5
_MIN_INDENT_PT = 8.0
_INDENT_FONT_RATIO = 0.6
_CENTER_TOLERANCE_RATIO = 0.08
_CENTER_MAX_WIDTH_RATIO = 0.7

# A line ending well short of the body's usual right margin is either the
# last line of a paragraph (expected) or, if it happens on an *internal*
# line, a sign the author broke the line deliberately -- the verse signal.
_SHORT_LINE_MARGIN_RATIO = 0.82
_FOOTNOTE_MARKER_CHARS = set("0123456789*†‡")


class DefaultParagraphReconstructor:
    """`ParagraphReconstructor` implementation."""

    def reconstruct(
        self, regions: list[LayoutRegion], stats: DocumentStats
    ) -> list[ParagraphCandidate]:
        body_margin = _compute_body_left_margin(regions)
        body_right_margin = _compute_body_right_margin(regions)
        indent_threshold = max(_MIN_INDENT_PT, stats.body_font_size * _INDENT_FONT_RATIO)
        page_width = stats.page_width

        def new_acc() -> "_Accumulator":
            return _Accumulator(body_margin, body_right_margin, indent_threshold, page_width)

        candidates: list[ParagraphCandidate] = []
        acc = new_acc()

        def flush() -> None:
            nonlocal acc
            if acc.has_content():
                candidates.append(acc.finalize())
            acc = new_acc()

        for region in regions:
            if region.region_type == RegionType.IMAGE:
                flush()
                if region.block.image is not None:
                    candidates.append(
                        ParagraphCandidate(
                            runs=[],
                            rough_kind=RoughKind.IMAGE,
                            source_pages=[region.page_index],
                            image=region.block.image,
                        )
                    )
                continue

            if region.region_type in (RegionType.HEADING_CANDIDATE, RegionType.FOOTNOTE):
                flush()
                rough_kind = (
                    RoughKind.HEADING_CANDIDATE
                    if region.region_type == RegionType.HEADING_CANDIDATE
                    else RoughKind.FOOTNOTE
                )
                isolated_acc = new_acc()
                for line in region.block.lines:
                    if line.spans:
                        isolated_acc.add_line(line, region.page_index, force_space_join=True)
                if isolated_acc.has_content():
                    candidates.append(isolated_acc.finalize(rough_kind=rough_kind))
                continue

            # BODY_TEXT
            for line in region.block.lines:
                if not line.spans:
                    continue
                if looks_like_scene_break(line.text):
                    # Always its own candidate, regardless of surrounding
                    # whitespace -- the marker text itself is the signal.
                    flush()
                    marker_acc = new_acc()
                    marker_acc.add_line(line, region.page_index, force_space_join=True)
                    candidates.append(marker_acc.finalize())
                    continue
                if acc.should_break(line, region.page_index):
                    flush()
                acc.add_line(line, region.page_index)

        flush()
        return candidates


@dataclass
class _Accumulator:
    body_margin: float
    body_right_margin: float
    indent_threshold: float
    page_width: float
    runs: list[Run] = field(default_factory=list)
    line_groups: list[list[Run]] = field(default_factory=list)
    source_pages: list[int] = field(default_factory=list)
    char_count: int = 0
    size_sum: float = 0.0
    max_size: float = 0.0
    bold_chars: int = 0
    first_line_bbox: BBox | None = None
    min_line_x0: float = float("inf")
    last_line_bbox: BBox | None = None
    last_line_page: int | None = None
    last_line_text: str = ""
    internal_short_lines: int = 0
    internal_line_count: int = 0
    _pending_line_was_short: bool = False

    def has_content(self) -> bool:
        return bool(self.runs)

    def should_break(self, line: RawLine, page_index: int) -> bool:
        if not self.runs or self.last_line_bbox is None:
            return False
        indented = line.bbox.x0 > self.body_margin + self.indent_threshold
        if self.last_line_page == page_index:
            gap = line.bbox.y0 - self.last_line_bbox.y1
            line_height = max(self.last_line_bbox.height, 1.0)
            if gap > line_height * _GAP_LINE_HEIGHT_RATIO:
                return True
            return indented and _ends_terminal(self.last_line_text)
        # Crossed a page boundary: default to continuing the paragraph
        # unless there's a clear new-paragraph signal.
        return indented and _ends_terminal(self.last_line_text)

    def add_line(self, line: RawLine, page_index: int, *, force_space_join: bool = False) -> None:
        started_new = not self.runs
        if started_new:
            self.first_line_bbox = line.bbox
        else:
            # The previously added line is now confirmed to have a line
            # after it -- it's "internal," not the paragraph's last line.
            self.internal_line_count += 1
            if self._pending_line_was_short:
                self.internal_short_lines += 1

        join_no_space = False
        if not started_new and not force_space_join:
            if hyphenation.ends_with_breaking_hyphen(
                self.last_line_text
            ) and hyphenation.should_dehyphenate(line.text):
                join_no_space = True
                self.runs[-1].text = self.runs[-1].text.rstrip()[:-1]
                if self.line_groups and self.line_groups[-1]:
                    self.line_groups[-1][-1].text = self.line_groups[-1][-1].text.rstrip()[:-1]

        line_runs: list[Run] = []
        for i, span in enumerate(line.spans):
            text = span.text
            if i == 0 and not started_new and not join_no_space:
                text = " " + text
            n = len(span.text.strip())
            if n:
                self.char_count += n
                self.size_sum += span.font_size * n
                self.max_size = max(self.max_size, span.font_size)
                if span.bold:
                    self.bold_chars += n

            footnote_ref = None
            stripped_span = span.text.strip()
            if (
                span.superscript
                and stripped_span
                and all(ch in _FOOTNOTE_MARKER_CHARS for ch in stripped_span)
            ):
                footnote_ref = stripped_span

            self.runs.append(
                Run(
                    text=text, italic=span.italic, bold=span.bold,
                    superscript=span.superscript, footnote_ref=footnote_ref,
                )
            )
            # Un-prefixed (no artificial join space) -- used for verse
            # rendering, where each line stands alone.
            line_runs.append(
                Run(
                    text=span.text, italic=span.italic, bold=span.bold,
                    superscript=span.superscript, footnote_ref=footnote_ref,
                )
            )

        self.line_groups.append(line_runs)
        self._pending_line_was_short = self._is_short_line(line.bbox)

        self.min_line_x0 = min(self.min_line_x0, line.bbox.x0)
        self.last_line_bbox = line.bbox
        self.last_line_page = page_index
        self.last_line_text = line.text
        if page_index not in self.source_pages:
            self.source_pages.append(page_index)

    def _is_short_line(self, bbox: BBox) -> bool:
        if self.body_right_margin <= 0:
            return False
        return bbox.x1 < self.body_right_margin * _SHORT_LINE_MARGIN_RATIO

    def finalize(self, rough_kind: RoughKind = RoughKind.BODY) -> ParagraphCandidate:
        avg_size = self.size_sum / self.char_count if self.char_count else 0.0
        bold_fraction = self.bold_chars / self.char_count if self.char_count else 0.0
        text = "".join(r.text for r in self.runs)
        stripped = text.strip()
        letters = [c for c in stripped if c.isalpha()]

        centered = False
        indented = False
        if self.first_line_bbox is not None:
            centered = _is_centered(self.first_line_bbox, self.page_width)
            indented = self.first_line_bbox.x0 > self.body_margin + self.indent_threshold

        # A single line sitting at the first-line-indent position is
        # indistinguishable from a block-indented quote until a *second*
        # line either confirms it (also shifted right) or disproves it
        # (back at the flush-left margin, i.e. an ordinary indented
        # paragraph). A lone short sentence is common and legitimate --
        # don't call it a blockquote on one line of evidence.
        block_indented = (
            len(self.line_groups) >= 2
            and self.min_line_x0 != float("inf")
            and (self.min_line_x0 - self.body_margin) > self.indent_threshold * 2
        )
        short_line_fraction = (
            self.internal_short_lines / self.internal_line_count
            if self.internal_line_count
            else 0.0
        )

        return ParagraphCandidate(
            runs=self.runs,
            rough_kind=rough_kind,
            source_pages=list(self.source_pages),
            max_font_size=self.max_size,
            avg_font_size=avg_size,
            bold_fraction=bold_fraction,
            centered=centered,
            indented=indented,
            block_indented=block_indented,
            starts_with_quote=bool(stripped) and stripped[0] in _QUOTE_START_CHARS,
            is_all_caps=bool(letters) and all(c.isupper() for c in letters),
            line_groups=self.line_groups,
            short_line_fraction=short_line_fraction,
        )


def _ends_terminal(text: str) -> bool:
    stripped = text.rstrip()
    if not stripped:
        return False
    if stripped[-1] in _TERMINAL_CHARS:
        return True
    # Some sources (plain-text-derived PDFs) render an em dash as "--".
    # A paragraph legitimately trailing off into dialogue with one ("he
    # said,--") is a real pattern, not a hyphenated line-wrap.
    return stripped.endswith("--")


def _is_centered(bbox: BBox, page_width: float) -> bool:
    if bbox.width >= page_width * _CENTER_MAX_WIDTH_RATIO:
        return False
    return abs(bbox.center_x - page_width / 2) < page_width * _CENTER_TOLERANCE_RATIO


def _compute_body_left_margin(regions: list[LayoutRegion]) -> float:
    """The most common line left-edge among body text -- the flush-left margin."""
    counts: Counter[float] = Counter()
    for region in regions:
        if region.region_type != RegionType.BODY_TEXT:
            continue
        for line in region.block.lines:
            if line.spans:
                counts[round(line.bbox.x0 / 2) * 2] += 1
    return counts.most_common(1)[0][0] if counts else 0.0


def _compute_body_right_margin(regions: list[LayoutRegion]) -> float:
    """The furthest-right a body text line commonly reaches -- the wrap margin.

    Uses a high percentile rather than the mode: most lines in a justified
    or ragged-right paragraph end at slightly different x1 values (only the
    *last* line of each paragraph reliably falls short), so no single value
    repeats the way the left margin does.
    """
    values: list[float] = []
    for region in regions:
        if region.region_type != RegionType.BODY_TEXT:
            continue
        for line in region.block.lines:
            if line.spans:
                values.append(line.bbox.x1)
    if not values:
        return 0.0
    values.sort()
    index = int(len(values) * 0.85)
    return values[min(index, len(values) - 1)]
