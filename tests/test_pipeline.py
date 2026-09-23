from __future__ import annotations

import pytest

from cozypdfs.models import (
    ChapterKind,
    Paragraph,
    ParagraphVariant,
    SceneBreak,
)
from cozypdfs.pipeline import ConversionPipeline

from .fixtures import BOOK_AUTHOR, BOOK_TITLE, HEADER_TEXT, build_novel_pdf


@pytest.fixture(scope="module")
def converted(tmp_path_factory):
    tmp_dir = tmp_path_factory.mktemp("cozypdfs_fixture")
    pdf_path = build_novel_pdf(tmp_dir / "the_quiet_harbor.pdf")
    epub_path = tmp_dir / "the_quiet_harbor.epub"

    events: list[tuple[str, str]] = []
    result = ConversionPipeline().convert(
        pdf_path, epub_path, on_progress=lambda stage, msg: events.append((stage, msg))
    )
    return result, events


def _block_text(block) -> str:
    return "".join(r.text for r in block.runs)


def test_progress_reports_every_stage(converted):
    _, events = converted
    stages = [stage for stage, _ in events]
    assert stages == [
        "analyze", "layout", "reading_order", "artifacts",
        "paragraphs", "structure", "epub", "validate", "done",
    ]


def test_metadata_extracted_from_title_page(converted):
    result, _ = converted
    assert result.book.metadata.title == BOOK_TITLE
    assert result.book.metadata.author == BOOK_AUTHOR


def test_two_chapters_detected(converted):
    result, _ = converted
    chapters = [c for c in result.book.chapters if c.kind != ChapterKind.FRONT_MATTER]
    assert len(chapters) == 2
    assert chapters[0].kind == ChapterKind.CHAPTER
    assert chapters[0].number == "1"
    assert chapters[1].number == "2"


def test_wrapped_lines_join_into_one_paragraph(converted):
    result, _ = converted
    ch1 = result.book.chapters[0]
    paragraphs = [b for b in ch1.blocks if isinstance(b, Paragraph)]
    texts = [_block_text(p) for p in paragraphs]
    assert (
        "The girl walked into the room and looked around, taking in the dust "
        "that had settled over every surface like a fine gray snow. Nothing "
        "here had moved in years, and the silence felt almost alive."
    ) in texts


def test_hyphenated_line_break_is_rejoined(converted):
    result, _ = converted
    ch1 = result.book.chapters[0]
    texts = [_block_text(p) for p in ch1.blocks if isinstance(p, Paragraph)]
    joined = " ".join(texts)
    assert "begun to peel away" in joined
    assert "be- gun" not in joined
    assert "begun to peel away" in joined


def test_cross_page_paragraph_stays_one_paragraph(converted):
    result, _ = converted
    ch1 = result.book.chapters[0]
    paragraphs = [b for b in ch1.blocks if isinstance(b, Paragraph)]
    texts = [_block_text(p) for p in paragraphs]
    assert (
        "She took a step forward, and then another, feeling the old "
        "floorboards creak beneath her weight with every movement."
    ) in texts


def test_scene_break_detected(converted):
    result, _ = converted
    ch1 = result.book.chapters[0]
    assert any(isinstance(b, SceneBreak) for b in ch1.blocks)


def test_dialogue_paragraph_variant(converted):
    result, _ = converted
    ch1 = result.book.chapters[0]
    dialogue = [
        b for b in ch1.blocks
        if isinstance(b, Paragraph) and b.variant == ParagraphVariant.DIALOGUE
    ]
    assert dialogue
    assert _block_text(dialogue[0]).startswith('"Is anyone there?"')


def test_italic_run_preserved(converted):
    result, _ = converted
    ch2 = result.book.chapters[1]
    paragraphs = [b for b in ch2.blocks if isinstance(b, Paragraph)]
    assert paragraphs
    italic_runs = [r for r in paragraphs[0].runs if r.italic]
    assert any(r.text == "impossible" for r in italic_runs)
    non_italic = [r for r in paragraphs[0].runs if not r.italic]
    assert any("whispered the word" in r.text for r in non_italic)


def test_running_header_and_page_numbers_removed(converted):
    result, _ = converted
    all_text = []
    for chapter in result.book.chapters:
        for block in chapter.blocks:
            if hasattr(block, "runs"):
                all_text.append(_block_text(block))
    joined = " ".join(all_text)
    assert HEADER_TEXT not in joined
    for chapter in result.book.chapters:
        for block in chapter.blocks:
            if isinstance(block, Paragraph):
                assert _block_text(block).strip() not in {"2", "3", "4"}


def test_no_coordinates_leak_into_book_model(converted):
    """The Book model must never carry PDF geometry -- spot check the dataclasses."""
    result, _ = converted
    for chapter in result.book.chapters:
        for block in chapter.blocks:
            assert not hasattr(block, "bbox")
            assert not hasattr(block, "page_index")
            assert not hasattr(block, "font_size")


def test_epub_is_valid(converted):
    result, _ = converted
    assert result.validation.is_valid, result.validation.errors
    assert result.epub_path.exists()


def test_epub_opens_with_ebooklib(converted):
    from ebooklib import epub

    result, _ = converted
    book = epub.read_epub(str(result.epub_path))
    assert book.get_metadata("DC", "title")[0][0] == BOOK_TITLE

    doc_items = list(book.get_items_of_type(9))  # ITEM_DOCUMENT
    combined = b" ".join(item.get_content() for item in doc_items)
    assert HEADER_TEXT.encode() not in combined
    assert "impossible".encode() in combined
