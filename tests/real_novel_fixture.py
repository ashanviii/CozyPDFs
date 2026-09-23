"""Builds a realistic test PDF from real, public-domain novel text.

Source: Project Gutenberg's "Pride and Prejudice" (Jane Austen, 1813; long
public domain), chapters I-III, trimmed to `fixtures_data/pride_and_prejudice_ch1-3.txt`
(https://www.gutenberg.org/ebooks/1342). Used only to exercise the
reconstruction pipeline against genuine prose -- varied sentence length,
heavy dialogue, `_emphasis_`-marked italics, an em-dash-terminated
paragraph introducing a new speaker -- rather than a hand-crafted fixture.
"""

from __future__ import annotations

import re
from pathlib import Path

from .typeset import BookTypesetter

HEADER_TEXT = "PRIDE AND PREJUDICE"
SOURCE_TEXT_PATH = Path(__file__).parent / "fixtures_data" / "pride_and_prejudice_ch1-3.txt"

_ILLUSTRATION_RE = re.compile(r"\[Illustration.*?\]\]", re.DOTALL)
_ILLUSTRATION_RE_SINGLE = re.compile(r"\[Illustration.*?\]", re.DOTALL)
_BLANK_LINES_RE = re.compile(r"\n\s*\n+")
_CHAPTER_I_START = "It is a truth universally acknowledged"


def _clean(text: str) -> str:
    text = _ILLUSTRATION_RE.sub("", text)
    text = _ILLUSTRATION_RE_SINGLE.sub("", text)
    return text


def _paragraphs(body: str) -> list[str]:
    cleaned = _clean(body)
    chunks = _BLANK_LINES_RE.split(cleaned)
    out = []
    for chunk in chunks:
        para = " ".join(chunk.split())
        if para:
            out.append(para)
    return out


def extract_chapters(raw_text: str, count: int = 3) -> list[tuple[str, list[str]]]:
    """Returns [(heading, [paragraph, ...]), ...] for the first `count` chapters."""
    start = raw_text.index(_CHAPTER_I_START)
    markers = [(f"CHAPTER {_roman(n)}.") for n in range(2, count + 2)]

    bounds = [start]
    for marker in markers:
        bounds.append(raw_text.index(marker, bounds[-1]))

    chapters = []
    for i in range(count):
        heading = f"CHAPTER {_roman(i + 1)}"
        body_start = bounds[i] if i == 0 else bounds[i] + len(markers[i - 1])
        body = raw_text[body_start : bounds[i + 1]]
        chapters.append((heading, _paragraphs(body)))
    return chapters


def _roman(n: int) -> str:
    table = [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    result = ""
    for value, symbol in table:
        while n >= value:
            result += symbol
            n -= value
    return result


def build_real_novel_pdf(source_txt: Path, out_pdf: Path, num_chapters: int = 3) -> Path:
    raw_text = source_txt.read_text(encoding="utf-8")
    chapters = extract_chapters(raw_text, num_chapters)

    ts = BookTypesetter(out_pdf, HEADER_TEXT)
    for heading, paragraphs in chapters:
        ts.heading(heading)
        for para in paragraphs:
            ts.paragraph(para)
    ts.save()
    return out_pdf
