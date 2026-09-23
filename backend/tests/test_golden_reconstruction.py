"""Golden-output tests: run the real reconstruction pipeline against the
small, on-disk PDF corpus in tests/golden_pdfs/ and assert on the
resulting DIR's actual structure and semantics — reading order, what got
merged into a paragraph, what got excluded as furniture, what fell back to
an image — not just "some text exists". See tests/golden_pdfs/builders.py
for how each fixture was built and why.
"""

from pathlib import Path

import pytest

from cozypdfs.conversion.pipeline import reconstruct_pdf
from cozypdfs.conversion.validation import validate
from cozypdfs.dir.schema import DIRDocument
from cozypdfs.storage.local import LocalDiskStorage

GOLDEN_DIR = Path(__file__).parent / "golden_pdfs"


def _reconstruct(name: str, storage: LocalDiskStorage) -> DIRDocument:
    data = (GOLDEN_DIR / f"{name}.pdf").read_bytes()
    return reconstruct_pdf(data, storage=storage, book_id=name, title=None, author=None)


def _blocks(document: DIRDocument) -> list:
    return [block for chapter in document.chapters for block in chapter.blocks]


def _contents(document: DIRDocument) -> list[str]:
    return [block.content for block in _blocks(document)]


# ---------------------------------------------------------------------
# 1. Normal single-column prose
# ---------------------------------------------------------------------


def test_single_column_prose_reconstructs_paragraphs_not_lines(storage: LocalDiskStorage):
    doc = _reconstruct("single_column_prose", storage)
    contents = _contents(doc)

    # Two lines belonging to one sentence must merge into one paragraph...
    assert any(
        "bright cold day" in c and "striking thirteen" in c and "town square below" in c
        for c in contents
    )
    # ...but a real paragraph break must NOT merge into the next paragraph.
    assert not any("clocks were striking thirteen" in c and "Winston walked" in c for c in contents)


def test_single_column_prose_merges_across_a_page_break_mid_sentence(storage: LocalDiskStorage):
    doc = _reconstruct("single_column_prose", storage)
    contents = _contents(doc)

    assert any(
        "He had almost reached the door" in c and "changed overnight" in c for c in contents
    ), "a sentence cut off at the bottom of a page must merge with its continuation on the next page"


def test_single_column_prose_does_not_merge_a_clean_paragraph_into_the_next_chapter(
    storage: LocalDiskStorage,
):
    doc = _reconstruct("single_column_prose", storage)
    contents = _contents(doc)

    assert not any("safely separated by a gap" in c and "second chapter opens" in c for c in contents)


def test_single_column_prose_splits_into_chapters_at_h1_headings(storage: LocalDiskStorage):
    doc = _reconstruct("single_column_prose", storage)
    titles = [chapter.title for chapter in doc.chapters]
    assert titles == ["Chapter One", "Chapter Two"]


def test_single_column_prose_has_no_pdf_page_boundary_artifacts(storage: LocalDiskStorage):
    doc = _reconstruct("single_column_prose", storage)
    # No block is a bare page-boundary marker, and the 3-page source never
    # produces more chapters than the 2 actual H1 headings warrant — a
    # naive "new page -> new chapter/block" rule would produce 3+.
    assert len(doc.chapters) == 2
    for block in _blocks(doc):
        assert block.content.strip() not in {"", "<p></p>"}
        assert not block.content.strip("<p>/ ").isdigit()


# ---------------------------------------------------------------------
# 2. Two-column document
# ---------------------------------------------------------------------


def test_two_column_reads_full_left_column_before_right_column(storage: LocalDiskStorage):
    doc = _reconstruct("two_column", storage)
    contents = _contents(doc)

    left_positions = [i for i, c in enumerate(contents) if "first finding" in c or "second observation" in c]
    right_positions = [i for i, c in enumerate(contents) if "second section" in c or "Results are discussed" in c]

    assert len(left_positions) == 2
    assert len(right_positions) == 2
    assert max(left_positions) < min(right_positions), "column 1 must be fully read before column 2 starts"


def test_two_column_does_not_interleave_by_line(storage: LocalDiskStorage):
    doc = _reconstruct("two_column", storage)
    contents = _contents(doc)
    # A naive y-then-x sort would interleave "finding"/"second section" at
    # the top row before either column's second line.
    assert not any("finding" in c and "methodology" in c for c in contents)


# ---------------------------------------------------------------------
# 3. Repeated headers and page numbers
# ---------------------------------------------------------------------


def test_repeated_header_and_page_numbers_are_removed(storage: LocalDiskStorage):
    doc = _reconstruct("headers_and_page_numbers", storage)
    contents = _contents(doc)

    assert not any("Reconstruction Journal" in c for c in contents)
    assert not any(block.content.strip() in {"1", "2", "3", "4", "5"} for block in _blocks(doc))


def test_repeated_header_body_content_is_retained_for_every_page(storage: LocalDiskStorage):
    doc = _reconstruct("headers_and_page_numbers", storage)
    contents = _contents(doc)

    for topic in ["ancient manuscript", "northern pass", "first three pages", "the margins", "capital city"]:
        assert any(topic in c for c in contents), f"body content about {topic!r} must survive"


# ---------------------------------------------------------------------
# 4. Footnotes
# ---------------------------------------------------------------------


def test_footnotes_are_kept_not_deleted_as_footers(storage: LocalDiskStorage):
    doc = _reconstruct("footnotes", storage)
    contents = _contents(doc)

    for marker in ["river that borders", "regional dialect", "appendix", "fire of 1889"]:
        assert any(marker in c for c in contents), f"footnote content {marker!r} must be retained"


def test_footnotes_are_typed_as_footnote_blocks(storage: LocalDiskStorage):
    doc = _reconstruct("footnotes", storage)
    footnote_blocks = [b for b in _blocks(doc) if b.type == "footnote"]
    assert len(footnote_blocks) == 4


def test_footnotes_do_not_delete_the_adjacent_body_paragraph(storage: LocalDiskStorage):
    doc = _reconstruct("footnotes", storage)
    contents = _contents(doc)
    for i in range(1, 5):
        assert any(f"unique to page {i}" in c for c in contents)


# ---------------------------------------------------------------------
# 5. Tables
# ---------------------------------------------------------------------


def test_simple_table_reconstructs_as_a_structured_table(storage: LocalDiskStorage):
    doc = _reconstruct("tables", storage)
    tables = [b for b in _blocks(doc) if b.type == "table"]
    assert len(tables) == 2

    clean = next(t for t in tables if not t.preserve_as_image)
    assert clean.confidence >= 0.9
    assert "<table>" in clean.content
    assert "John" in clean.content and "24" in clean.content and "India" in clean.content
    assert "Sarah" in clean.content and "UK" in clean.content
    # Never flattened into meaningless run-on text.
    assert "Name Age Country John 24 India" not in clean.content


def test_complex_table_falls_back_to_preserved_image(storage: LocalDiskStorage):
    doc = _reconstruct("tables", storage)
    tables = [b for b in _blocks(doc) if b.type == "table"]

    messy = next(t for t in tables if t.preserve_as_image)
    assert messy.confidence < 0.9
    assert messy.asset_id is not None
    assert messy.content == ""


def test_table_caption_is_associated_with_the_table(storage: LocalDiskStorage):
    doc = _reconstruct("tables", storage)
    blocks = _blocks(doc)
    table_index = next(i for i, b in enumerate(blocks) if b.type == "table")
    assert blocks[table_index + 1].type == "caption"
    assert "Participant summary" in blocks[table_index + 1].content


# ---------------------------------------------------------------------
# 6. Equations
# ---------------------------------------------------------------------


def test_equation_is_preserved_as_an_image(storage: LocalDiskStorage):
    doc = _reconstruct("equations", storage)
    equations = [b for b in _blocks(doc) if b.type == "equation"]
    assert len(equations) == 1
    assert equations[0].preserve_as_image is True
    assert equations[0].asset_id is not None
    assert len(doc.assets) == 1


def test_prose_around_an_equation_stays_readable_text(storage: LocalDiskStorage):
    doc = _reconstruct("equations", storage)
    blocks = _blocks(doc)
    types = [b.type for b in blocks]

    assert types == ["paragraph", "equation", "paragraph"]
    assert "Pythagorean" in blocks[2].content
    assert blocks[2].type != "caption"  # prose after an equation is not a caption


# ---------------------------------------------------------------------
# 7. Figures with captions
# ---------------------------------------------------------------------


def test_each_figure_is_immediately_followed_by_its_caption(storage: LocalDiskStorage):
    doc = _reconstruct("figures_with_captions", storage)
    blocks = _blocks(doc)

    figure_indices = [i for i, b in enumerate(blocks) if b.type == "figure"]
    assert len(figure_indices) == 2
    for i in figure_indices:
        assert blocks[i + 1].type == "caption"

    assert "Site A" in blocks[figure_indices[0] + 1].content
    assert "Site B" in blocks[figure_indices[1] + 1].content


def test_paragraph_between_figures_is_not_swallowed_as_a_caption(storage: LocalDiskStorage):
    doc = _reconstruct("figures_with_captions", storage)
    contents = _contents(doc)
    assert any("separates the two figures" in c for c in contents)


# ---------------------------------------------------------------------
# 8. Maps / diagrams / complex visual content
# ---------------------------------------------------------------------


def test_complex_visual_is_preserved_never_ocrd(storage: LocalDiskStorage):
    doc = _reconstruct("complex_visual", storage)
    figures = [b for b in _blocks(doc) if b.type == "figure"]
    assert len(figures) == 1
    assert figures[0].preserve_as_image is True
    assert figures[0].content == ""  # never any attempted text extraction

    captions = [b for b in _blocks(doc) if b.type == "caption"]
    assert len(captions) == 1
    assert "Survey regions" in captions[0].content


# ---------------------------------------------------------------------
# 9. Mixed layouts
# ---------------------------------------------------------------------


def test_mixed_layout_interprets_each_page_locally_in_correct_order(storage: LocalDiskStorage):
    doc = _reconstruct("mixed_layout", storage)
    contents = _contents(doc)

    def index_of(fragment: str) -> int:
        return next(i for i, c in enumerate(contents) if fragment in c)

    intro = index_of("introduces the topic")
    left_col = index_of("stays on the left")
    right_col = index_of("stays on the right")
    table_intro = index_of("summarizes the comparison")
    closing = index_of("returns to single-column")

    assert intro < left_col < right_col < table_intro < closing


def test_mixed_layout_table_page_reconstructs_the_table(storage: LocalDiskStorage):
    doc = _reconstruct("mixed_layout", storage)
    tables = [b for b in _blocks(doc) if b.type == "table"]
    assert len(tables) == 1
    assert "Speed" in tables[0].content and "42" in tables[0].content


# ---------------------------------------------------------------------
# 10. A deliberately difficult PDF
# ---------------------------------------------------------------------


def test_difficult_pdf_does_not_crash_and_produces_a_valid_dir(storage: LocalDiskStorage):
    doc = _reconstruct("difficult", storage)
    assert validate(doc) == []


def test_difficult_pdf_ambiguous_columns_do_not_produce_a_confident_wrong_split(
    storage: LocalDiskStorage,
):
    """A three-column page must not be detected as a clean two-column
    layout — that would produce a confidently wrong, systematically
    interleaved reading order. Falling back to single-flow (imperfect,
    but not systematically wrong) is the required safe degradation."""
    doc = _reconstruct("difficult", storage)
    contents = _contents(doc)
    # The wrong-but-plausible failure mode this guards against: column A
    # and column C's *first* lines ending up adjacent to each other while
    # skipping column B entirely, which is what a bad binary column split
    # would produce.
    assert not any("colA line one" in c and "colC line one" in c and "colB" not in c for c in contents)


def test_difficult_pdf_heading_list_and_table_packed_together_are_still_distinguished(
    storage: LocalDiskStorage,
):
    doc = _reconstruct("difficult", storage)
    blocks = _blocks(doc)
    types_on_last_chapter = [b.type for b in doc.chapters[-1].blocks]
    assert "list" in types_on_last_chapter
    assert "table" in types_on_last_chapter

    list_block = next(b for b in blocks if b.type == "list")
    assert "<li>first point</li>" in list_block.content
    assert "<li>second point</li>" in list_block.content


ALL_GOLDEN_NAMES = [
    "single_column_prose",
    "two_column",
    "headers_and_page_numbers",
    "footnotes",
    "tables",
    "equations",
    "figures_with_captions",
    "complex_visual",
    "mixed_layout",
    "difficult",
    "three_column",
    "uneven_three_column",
    "mixed_column_counts",
    "realistic_book_excerpt",
]


def test_all_golden_pdfs_produce_a_valid_dir(storage: LocalDiskStorage):
    for name in ALL_GOLDEN_NAMES:
        doc = _reconstruct(name, storage)
        issues = validate(doc)
        assert issues == [], f"{name}: {[i.message for i in issues]}"


# ---------------------------------------------------------------------
# N-column reading order
# ---------------------------------------------------------------------


def test_one_column_stays_single_flow(storage: LocalDiskStorage):
    """Sanity check: N-column detection must not fire on ordinary
    single-column prose (single_column_prose.pdf already covers this in
    depth; this just asserts the column count directly)."""
    doc = _reconstruct("single_column_prose", storage)
    contents = _contents(doc)
    assert any("bright cold day" in c for c in contents)


def test_three_column_reads_each_column_fully_in_order(storage: LocalDiskStorage):
    doc = _reconstruct("three_column", storage)
    contents = _contents(doc)

    def index_of(fragment: str) -> int:
        return next(i for i, c in enumerate(contents) if fragment in c)

    alpha = index_of("Alpha section")
    beta = index_of("Beta section")
    gamma = index_of("Gamma section")
    assert alpha < beta < gamma

    # Each column's own two lines merged into one paragraph, not split or
    # cross-contaminated with another column's text.
    assert any("Alpha section" in c and "Second alpha" in c and "Beta" not in c for c in contents)
    assert any("Beta section" in c and "Second beta" in c and "Gamma" not in c and "Alpha" not in c for c in contents)
    assert any("Gamma section" in c and "Second gamma" in c and "Beta" not in c for c in contents)


def test_three_column_does_not_interleave_by_row(storage: LocalDiskStorage):
    doc = _reconstruct("three_column", storage)
    contents = _contents(doc)
    # A row-major (y-then-x) sort would put all three columns' "line one"
    # before any column's "Second ..." line — assert that never happens.
    assert not any("Alpha section" in c and "Beta section" in c for c in contents)


def test_uneven_three_column_tolerates_different_widths_and_content_amounts(
    storage: LocalDiskStorage,
):
    doc = _reconstruct("uneven_three_column", storage)
    contents = _contents(doc)

    def index_of(fragment: str) -> int:
        return next(i for i, c in enumerate(contents) if fragment in c)

    narrow = index_of("Narrow col")
    wide_middle = index_of("wide middle column")
    right = index_of("Right column")
    assert narrow < wide_middle < right

    # The narrow column's 2 short lines and the wide column's 4 long
    # lines each merge into exactly one paragraph despite the size
    # mismatch between columns.
    assert any(c.count("Narrow col") == 1 and "line one." in c for c in contents)
    assert any("wide middle column" in c and "share of the page width here" in c for c in contents)


def test_mixed_column_counts_decides_independently_per_page(storage: LocalDiskStorage):
    doc = _reconstruct("mixed_column_counts", storage)
    contents = _contents(doc)

    def index_of(fragment: str) -> int:
        return next(i for i, c in enumerate(contents) if fragment in c)

    # Section A (1 column): the two lines merge into one paragraph.
    assert any(
        "ordinary single-column prose" in c and "nothing unusual" in c for c in contents
    )

    # Section B (2 columns): left fully before right.
    left = index_of("Left half")
    right = index_of("Right half")
    assert left < right
    assert any("Left half line one" in c and "left half line two" in c for c in contents)

    # Section C (3 columns): First, Second, Third in order, each intact.
    first = index_of("First col")
    second = index_of("Second col")
    third = index_of("Third col")
    assert first < second < third
    assert any("First col line one" in c and "First col line two" in c for c in contents)


def test_difficult_pdf_three_column_page_now_reads_cleanly(storage: LocalDiskStorage):
    """The N-column algorithm resolves what Phase 2A's binary-split
    version could only safely degrade on (see the earlier report's known
    limitation) — the three near-equal columns on difficult.pdf's first
    page now read in full, correct column order."""
    doc = _reconstruct("difficult", storage)
    contents = _contents(doc)

    def index_of(fragment: str) -> int:
        return next(i for i, c in enumerate(contents) if fragment in c)

    a = index_of("colA line one")
    b = index_of("colB line one")
    c = index_of("colC line one")
    assert a < b < c
    assert any("colA line one" in text and "colA line two" in text for text in contents)
    assert not any("colA" in text and "colB" in text for text in contents)


# ---------------------------------------------------------------------
# A more natural, longer prose sample
# ---------------------------------------------------------------------


def test_realistic_book_excerpt_reads_as_natural_continuous_prose(storage: LocalDiskStorage):
    doc = _reconstruct("realistic_book_excerpt", storage)
    contents = _contents(doc)

    assert len(contents) == 4  # 4 paragraphs, correctly separated
    assert any("eleven winters" in c and "gathering its strength" in c for c in contents)
    assert any(
        "convinced herself it was nothing" in c and "not to think about too closely" in c
        for c in contents
    )
    # No block is an orphaned single line or a fragment of another paragraph.
    for c in contents:
        assert c.startswith("<p>") and c.endswith("</p>")


def test_reconstruction_is_deterministic(storage: LocalDiskStorage, tmp_path):
    data = (GOLDEN_DIR / "single_column_prose.pdf").read_bytes()
    other_storage = LocalDiskStorage(tmp_path / "storage2")

    first = reconstruct_pdf(data, storage=storage, book_id="det", title="T", author="A")
    second = reconstruct_pdf(data, storage=other_storage, book_id="det", title="T", author="A")

    assert first.model_dump() == second.model_dump()


@pytest.mark.parametrize("name", list(GOLDEN_DIR.glob("*.pdf")), ids=lambda p: p.stem)
def test_golden_corpus_file_exists_and_is_a_real_pdf(name: Path):
    assert name.exists()
    assert name.read_bytes()[:5] == b"%PDF-"
