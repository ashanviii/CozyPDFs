"""Stage 4: PDF-artifact removal.

Detects and drops repeated running headers, running footers, and page
numbers using frequency + position analysis: a header/footer-zone block
is only removed if the same (normalized) text recurs across a meaningful
fraction of pages. A one-off block that merely happens to sit in the
header/footer zone -- a footnote, a stray caption -- is not a repeated
artifact, so it is kept and reclassified as ordinary body text rather than
being silently discarded.

Page numbers are handled separately: `regions.py` already narrowly
classifies a block as `PAGE_NUMBER` only when it sits in the header/footer
zone AND is purely numeric or a roman numeral, so those are dropped
unconditionally -- that classification is specific enough to not need a
frequency check.
"""

from __future__ import annotations

import re
from collections import defaultdict

from ..models import LayoutRegion, RegionType

_MIN_OCCURRENCES = 3
_MIN_PAGE_FRACTION = 0.3

_DIGIT_RUN_RE = re.compile(r"\d+")
_WHITESPACE_RE = re.compile(r"\s+")


class DefaultArtifactRemover:
    """`ArtifactRemover` implementation using frequency + position analysis."""

    def remove(self, regions: list[LayoutRegion]) -> list[LayoutRegion]:
        total_pages = len({r.page_index for r in regions}) or 1
        pattern_pages: dict[tuple[RegionType, str], set[int]] = defaultdict(set)

        for region in regions:
            if region.region_type in (RegionType.HEADER, RegionType.FOOTER):
                key = (region.region_type, _normalize(_region_text(region)))
                pattern_pages[key].add(region.page_index)

        repeated_keys = {
            key
            for key, pages in pattern_pages.items()
            if len(pages) >= _MIN_OCCURRENCES and len(pages) / total_pages >= _MIN_PAGE_FRACTION
        }

        result: list[LayoutRegion] = []
        for region in regions:
            if region.region_type == RegionType.PAGE_NUMBER:
                continue

            if region.region_type in (RegionType.HEADER, RegionType.FOOTER):
                key = (region.region_type, _normalize(_region_text(region)))
                if key in repeated_keys:
                    continue
                # Not a repeated pattern -- likely one-off content (a
                # footnote, a stray caption). Keep it as body text rather
                # than discarding it.
                region.region_type = RegionType.BODY_TEXT

            result.append(region)

        return result


def _region_text(region: LayoutRegion) -> str:
    return " ".join(line.text for line in region.block.lines).strip()


def _normalize(text: str) -> str:
    """Fold running-header variations that only differ by a changing number.

    A running header like "Chapter 3" vs "Chapter 4" is still the same
    repeated pattern -- only the chapter number changes page to page --
    so digit runs are collapsed to a placeholder before comparing.
    """
    normalized = _DIGIT_RUN_RE.sub("#", text.strip().casefold())
    return _WHITESPACE_RE.sub(" ", normalized)
