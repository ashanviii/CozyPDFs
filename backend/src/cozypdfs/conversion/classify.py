"""Semantic reconstruction, line-level pass: refines BODY-role lines in the
already-ordered sequence into HEADING / LIST_ITEM / EQUATION, in place.
Runs after reading-order so it only ever looks at real reading order, never
raw page position — heading-size statistics are still document-global,
computed once up front.

Deliberately conservative: a line only becomes a heading when its size is
both distinctly larger than the body text AND short (long, larger-font
lines are just as often pull-quotes or emphasis, not structure). Distinct
larger sizes are bucketed into at most 3 heading levels — enough to
represent "title / section / subsection" without inventing a hierarchy the
source doesn't clearly have.
"""

import re

from cozypdfs.conversion.types import ClassifiedLine, LineRole, OrderedItem

_MATH_SYMBOLS = set("∑∫√±≤≥≠∞∂→×÷" "αβγδεζηθικλμνξοπρστυφχψω" "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ")
_MATH_OPERATOR_TOKEN = set("=+-*/^<>≤≥≠±")
_MATH_VARIABLE_RE = re.compile(r"^[a-zA-Z]\^?\d+$")  # e.g. "x^2", "y2" — a short variable/exponent token
_MATH_TOKEN_DENSITY_THRESHOLD = 0.5
_MIN_MATH_TOKENS = 3

_BULLET_CHARS = "•‣◦▪–-*·"
_NUMBERED_LIST_RE = re.compile(r"^\s*(\d{1,3}|[a-zA-Z])[.)]\s+")

_HEADING_MAX_WORDS = 15
_HEADING_SIZE_RATIO = 1.1
_MAX_HEADING_LEVELS = 3


def classify_items(items: list[OrderedItem], dominant_body_size: float) -> list[OrderedItem]:
    level_by_size = _heading_levels(items, dominant_body_size)

    result: list[OrderedItem] = []
    for item in items:
        if not isinstance(item, ClassifiedLine) or item.role != LineRole.BODY:
            result.append(item)
            continue
        result.append(_classify_body_line(item, level_by_size))
    return result


def _heading_levels(items: list[OrderedItem], dominant_body_size: float) -> dict[float, int]:
    sizes = sorted(
        {
            round(item.line.size, 1)
            for item in items
            if isinstance(item, ClassifiedLine)
            and item.role == LineRole.BODY
            and item.line.size > dominant_body_size * _HEADING_SIZE_RATIO
        },
        reverse=True,
    )
    return {size: min(index + 1, _MAX_HEADING_LEVELS) for index, size in enumerate(sizes)}


def _classify_body_line(item: ClassifiedLine, level_by_size: dict[float, int]) -> ClassifiedLine:
    text = item.line.text.strip()
    if not text:
        return item

    if _looks_like_equation(text):
        return ClassifiedLine(line=item.line, role=LineRole.EQUATION)

    size = round(item.line.size, 1)
    word_count = len(text.split())
    is_sized_heading = size in level_by_size and word_count <= _HEADING_MAX_WORDS and not text.endswith((".", ",", ";"))
    is_bold_heading = item.line.bold and word_count <= 8 and not text.endswith((".", ",", ";"))

    if is_sized_heading:
        return ClassifiedLine(line=item.line, role=LineRole.HEADING, heading_level=level_by_size[size])
    if is_bold_heading:
        return ClassifiedLine(line=item.line, role=LineRole.HEADING, heading_level=_MAX_HEADING_LEVELS)

    marker, indent = _list_marker(text, item.line.bbox.x0)
    if marker:
        return ClassifiedLine(line=item.line, role=LineRole.LIST_ITEM, list_marker=marker, list_indent=indent)

    return item


def _looks_like_equation(text: str) -> bool:
    """Two independent signals, either sufficient on its own: a real
    Unicode math/Greek symbol anywhere (reliable when the source PDF
    embeds a font with proper glyph coverage, which most PDFs producing
    genuine equations do — LaTeX, Word's equation editor, etc.), or a high
    fraction of ASCII tokens that look like variables/operators rather
    than words (font-independent, so it still catches equations set in a
    base font too limited to encode Unicode math glyphs at all)."""
    if any(ch in _MATH_SYMBOLS for ch in text):
        return True

    tokens = text.split()
    if len(tokens) < _MIN_MATH_TOKENS:
        return False
    math_like = sum(1 for token in tokens if _is_math_token(token))
    return math_like / len(tokens) >= _MATH_TOKEN_DENSITY_THRESHOLD


def _is_math_token(token: str) -> bool:
    if all(ch in _MATH_OPERATOR_TOKEN for ch in token):
        return True
    return bool(_MATH_VARIABLE_RE.match(token))


def _list_marker(text: str, indent: float) -> tuple[str | None, float]:
    if text and text[0] in _BULLET_CHARS and (len(text) == 1 or text[1] == " "):
        return text[0], indent
    match = _NUMBERED_LIST_RE.match(text)
    if match:
        return match.group(0).strip(), indent
    return None, 0.0
