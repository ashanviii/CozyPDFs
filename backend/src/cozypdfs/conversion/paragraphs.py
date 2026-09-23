"""Paragraph reconstruction primitives: deciding whether two consecutive
lines belong to the same paragraph, and joining their text (including
undoing mid-word hyphenation at a line break). Used by semantic.py, which
owns the actual walk over the ordered sequence — these are pure functions
so each rule is independently testable.

Paragraph continuation deliberately treats a page break as "probably the
same paragraph" whenever the previous line was cut off mid-sentence, and
"probably a new paragraph" when it wasn't — per the product rule that a PDF
page boundary is not a reading boundary, gluing a genuinely finished
sentence to unrelated text on the next page is worse than an extra
paragraph break.
"""

from collections import Counter
from itertools import pairwise

from cozypdfs.conversion.types import ClassifiedLine

_GAP_BREAK_RATIO = 1.4
_INDENT_BREAK_RATIO = 1.5
_SENTENCE_END = (".", "!", "?", "”", "'", '"')


def typical_line_gap(lines: list[ClassifiedLine]) -> float:
    """The baseline "this is just normal line spacing" gap, used to
    recognize a larger gap as a paragraph break.

    Deliberately the *mode*, not the median: in ordinary prose, gaps
    between wrapped lines within a paragraph vastly outnumber gaps between
    paragraphs, so the single-line gap is the most frequent value — the
    median can land on (or near) the less-common paragraph-gap value
    instead when a document has relatively few, short paragraphs.

    Gaps are NOT filtered to positive values: consecutive wrapped lines
    routinely have a slightly negative bbox gap (one line's descender
    extent overlaps the next line's ascender extent), and that negative
    value is exactly the "normal spacing" sample this function needs —
    discarding it left too few samples to form a reliable mode."""
    gaps: list[float] = []
    for prev, curr in pairwise(lines):
        if prev.line.page_number != curr.line.page_number:
            continue
        gap = curr.line.bbox.y0 - prev.line.bbox.y1
        gaps.append(round(gap * 2) / 2)  # bucket to the nearest 0.5pt
    if not gaps:
        return 4.0

    winner, count = Counter(gaps).most_common(1)[0]
    if count < 2:
        # Too few same-page line pairs to trust a "most common" value at
        # all (every gap is unique) — a small fixed baseline biases
        # towards treating gaps as paragraph breaks, which is the safer
        # failure mode than gluing unrelated short fragments together.
        return 4.0
    return winner


def is_continuation(prev: ClassifiedLine, curr: ClassifiedLine, typical_gap: float) -> bool:
    if prev.line.page_number != curr.line.page_number:
        prev_text = prev.line.text.strip()
        return not prev_text.endswith(_SENTENCE_END)

    gap = curr.line.bbox.y0 - prev.line.bbox.y1
    # `typical_gap` can itself be at or below zero (overlapping bbox
    # extents are normal single-line spacing), so scaling it up must not
    # be allowed to produce a threshold that's *more* negative than the
    # baseline — floor it at a small positive value like the indent check
    # below already does.
    gap_break_threshold = max(typical_gap * _GAP_BREAK_RATIO, 4.0)
    if gap > gap_break_threshold:
        return False

    indent_delta = curr.line.bbox.x0 - prev.line.bbox.x0
    return indent_delta <= max(typical_gap * _INDENT_BREAK_RATIO, 6.0)


def join_text(lines: list[ClassifiedLine]) -> str:
    result = ""
    for classified in lines:
        text = classified.line.text.strip()
        if not text:
            continue
        if result.endswith("-") and len(result) >= 2 and result[-2].isalpha() and text[:1].islower():
            result = result[:-1] + text
        elif result:
            result = result + " " + text
        else:
            result = text
    return result
