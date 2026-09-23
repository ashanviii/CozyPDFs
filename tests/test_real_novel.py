"""Regression test against real, unmodified 19th-century prose.

The synthetic fixture in `test_pipeline.py` exercises specific mechanics
in isolation. This exercises the same pipeline against real text with all
its irregularities at once -- varied paragraph and sentence length, heavy
back-and-forth dialogue, single-sentence paragraphs, `_emphasis_` italics,
and a paragraph that legitimately ends in an em dash before introducing a
new line of dialogue. Two real bugs were found and fixed this way that no
hand-crafted fixture surfaced: a single-sentence paragraph being
misclassified as a blockquote, and an em-dash-terminated paragraph merging
into the next one.
"""

from __future__ import annotations

import re

import pytest

from cozypdfs.models import Paragraph, ParagraphVariant
from cozypdfs.pipeline import ConversionPipeline

from .real_novel_fixture import HEADER_TEXT, SOURCE_TEXT_PATH, build_real_novel_pdf, extract_chapters

_ITALIC_MARKER_RE = re.compile(r"_([^_]+)_")


def _strip_italic_markers(text: str) -> str:
    return _ITALIC_MARKER_RE.sub(r"\1", text)


@pytest.fixture(scope="module")
def source_chapters():
    raw = SOURCE_TEXT_PATH.read_text(encoding="utf-8")
    return extract_chapters(raw, 3)


@pytest.fixture(scope="module")
def converted(tmp_path_factory, source_chapters):
    tmp_dir = tmp_path_factory.mktemp("real_novel")
    pdf_path = build_real_novel_pdf(SOURCE_TEXT_PATH, tmp_dir / "pride.pdf", num_chapters=3)
    result = ConversionPipeline().convert(pdf_path, tmp_dir / "pride.epub")
    return result


def test_all_three_chapters_detected(converted):
    chapters = converted.book.chapters
    assert [c.number for c in chapters] == ["1", "2", "3"]


def test_paragraph_count_matches_source_exactly(converted, source_chapters):
    for chapter, (heading, src_paras) in zip(converted.book.chapters, source_chapters):
        paragraphs = [b for b in chapter.blocks if isinstance(b, Paragraph)]
        assert len(paragraphs) == len(src_paras), (
            f"{heading}: expected {len(src_paras)} paragraphs, got {len(paragraphs)} "
            f"(a paragraph split or merged incorrectly)"
        )


def test_paragraph_text_matches_source(converted, source_chapters):
    """Reconstructed text must equal the source, modulo italic markers
    becoming real Run.italic flags -- no words dropped, no words merged,
    no paragraphs collapsed together."""
    for chapter, (heading, src_paras) in zip(converted.book.chapters, source_chapters):
        paragraphs = [b for b in chapter.blocks if isinstance(b, Paragraph)]
        for src, block in zip(src_paras, paragraphs):
            expected = _strip_italic_markers(src)
            actual = "".join(r.text for r in block.runs)
            assert actual == expected, f"{heading}: mismatch\n  expected: {expected!r}\n  actual:   {actual!r}"


def test_no_paragraph_misclassified_as_blockquote(converted):
    """Every block in this text is an ordinary paragraph -- there are no
    genuine block quotations. A single short sentence must not be
    misread as one just because it sits at the first-line-indent position."""
    for chapter in converted.book.chapters:
        for block in chapter.blocks:
            assert isinstance(block, Paragraph), f"unexpected block type: {type(block).__name__}"


def test_italic_emphasis_preserved(converted):
    all_italic_words = set()
    for chapter in converted.book.chapters:
        for block in chapter.blocks:
            if isinstance(block, Paragraph):
                for run in block.runs:
                    if run.italic:
                        all_italic_words.add(run.text.strip())
    assert "You" in all_italic_words
    assert "may" in all_italic_words


def test_dialogue_detected(converted):
    dialogue_count = sum(
        1
        for chapter in converted.book.chapters
        for block in chapter.blocks
        if isinstance(block, Paragraph) and block.variant == ParagraphVariant.DIALOGUE
    )
    assert dialogue_count > 20  # this text is dialogue-heavy


def test_running_header_and_page_numbers_stripped(converted):
    for chapter in converted.book.chapters:
        for block in chapter.blocks:
            if isinstance(block, Paragraph):
                text = "".join(r.text for r in block.runs).strip()
                assert HEADER_TEXT not in text
                assert not text.isdigit()


def test_epub_valid(converted):
    assert converted.validation.is_valid, converted.validation.errors
