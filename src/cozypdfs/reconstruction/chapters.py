"""Chapter-boundary detection.

Not every large or bold piece of text is a chapter heading -- a pull quote,
a subheading, an emphasized aside can all trigger the layout stage's
`HEADING_CANDIDATE` classification. This module narrows that down to
headings that actually *read* like the start of a chapter: "Chapter One",
"CHAPTER 3", "Part II", "Prologue", "Epilogue", or a standalone number/
roman numeral. A heading candidate that matches none of these stays a
heading inside the current chapter rather than starting a new one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import ChapterKind

_WORD_NUMBERS = {
    word: i
    for i, word in enumerate(
        [
            "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
            "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
            "sixteen", "seventeen", "eighteen", "nineteen", "twenty",
        ]
    )
}
_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}

_CHAPTER_RE = re.compile(
    r"^(chapter|part|book)\s+([ivxlcdm]+|\d+|[a-z\-]+)\s*[:.—\-]?\s*(.*)$",
    re.IGNORECASE,
)
_PROLOGUE_RE = re.compile(r"^(prologue)\b\s*[:.—\-]?\s*(.*)$", re.IGNORECASE)
_EPILOGUE_RE = re.compile(r"^(epilogue)\b\s*[:.—\-]?\s*(.*)$", re.IGNORECASE)
_STANDALONE_NUM_RE = re.compile(r"^(\d{1,3}|[ivxlcdm]{1,7})$", re.IGNORECASE)


@dataclass(slots=True)
class HeadingClassification:
    kind: ChapterKind
    number: str | None
    title: str | None


def classify_heading(text: str) -> HeadingClassification | None:
    """Return how `text` should be treated as a chapter start, or None."""
    t = " ".join(text.split()).strip()
    if not t:
        return None

    if m := _PROLOGUE_RE.match(t):
        return HeadingClassification(ChapterKind.PROLOGUE, None, m.group(2).strip() or None)
    if m := _EPILOGUE_RE.match(t):
        return HeadingClassification(ChapterKind.EPILOGUE, None, m.group(2).strip() or None)
    if m := _CHAPTER_RE.match(t):
        number = _resolve_number(m.group(2))
        title = m.group(3).strip() or None
        return HeadingClassification(ChapterKind.CHAPTER, number, title)
    if _STANDALONE_NUM_RE.match(t):
        return HeadingClassification(ChapterKind.CHAPTER, _resolve_number(t), None)
    return None


def _resolve_number(raw: str) -> str:
    raw_clean = raw.strip()
    if raw_clean.isdigit():
        return raw_clean
    lowered = raw_clean.lower()
    if lowered in _WORD_NUMBERS:
        return str(_WORD_NUMBERS[lowered])
    roman = _roman_to_int(lowered)
    if roman is not None:
        return str(roman)
    return raw_clean


def _roman_to_int(s: str) -> int | None:
    if not s or any(c not in _ROMAN_VALUES for c in s):
        return None
    total = 0
    prev = 0
    for char in reversed(s):
        value = _ROMAN_VALUES[char]
        total += value if value >= prev else -value
        prev = value
    return total if total > 0 else None
