"""Phase 2B: DIR -> ReaderArtifact derivation.

Two kinds of coverage here:

1. Golden-corpus scenario tests — run the real Phase 2A reconstruction
   pipeline against tests/golden_pdfs/, then derive a ReaderArtifact and
   assert on its actual structure (order, merged captions, block types),
   the same "assert on real semantics, not just presence" standard as
   test_golden_reconstruction.py.
2. A synthetic-DIR test for multi-level heading -> nested section folding,
   because no golden PDF fixture currently has H2/H3 sub-headings — this
   formalizes the manual smoke test the folding algorithm was originally
   verified against.

A single "semantic preservation" test then sweeps the whole golden corpus
and proves, block by block, that derivation is a pure re-shaping: the same
text, same order, same confidence/provenance survive from DIR into the
artifact. Representation may change (nesting, caption merging) — meaning
must not.
"""

from pathlib import Path

from cozypdfs.conversion.pipeline import reconstruct_pdf
from cozypdfs.dir.schema import Block as DIRBlock
from cozypdfs.dir.schema import BlockType as DIRBlockType
from cozypdfs.dir.schema import Chapter as DIRChapter
from cozypdfs.dir.schema import DIRDocument, DIRMeta
from cozypdfs.reader_artifact.build import derive_reader_artifact
from cozypdfs.reader_artifact.schema import (
    ReaderBlock,
    ReaderBlockType,
    ReaderSection,
)
from cozypdfs.storage.local import LocalDiskStorage

GOLDEN_DIR = Path(__file__).parent / "golden_pdfs"

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


def _reconstruct(name: str, storage: LocalDiskStorage) -> DIRDocument:
    data = (GOLDEN_DIR / f"{name}.pdf").read_bytes()
    return reconstruct_pdf(data, storage=storage, book_id=name, title=None, author=None)


def _dir_blocks(document: DIRDocument) -> list[DIRBlock]:
    return [block for chapter in document.chapters for block in chapter.blocks]


def _artifact_blocks(sections: list[ReaderSection]) -> list[ReaderBlock]:
    out: list[ReaderBlock] = []
    for section in sections:
        out.extend(section.blocks)
        out.extend(_artifact_blocks(section.children))
    return out


# ---------------------------------------------------------------------
# Golden-corpus scenarios
# ---------------------------------------------------------------------


def test_single_column_prose_chapters_become_top_level_sections(storage: LocalDiskStorage):
    doc = _reconstruct("single_column_prose", storage)
    artifact = derive_reader_artifact(doc, book_id="single_column_prose")

    assert [s.title for s in artifact.sections] == ["Chapter One", "Chapter Two"]
    assert all(s.level == 1 for s in artifact.sections)


def test_two_column_block_order_matches_dir_reading_order(storage: LocalDiskStorage):
    doc = _reconstruct("two_column", storage)
    artifact = derive_reader_artifact(doc, book_id="two_column")

    dir_contents = [b.content for b in _dir_blocks(doc)]
    artifact_contents = [b.content for b in _artifact_blocks(artifact.sections)]
    assert artifact_contents == dir_contents


def test_footnotes_survive_as_footnote_blocks_in_original_order(storage: LocalDiskStorage):
    doc = _reconstruct("footnotes", storage)
    artifact = derive_reader_artifact(doc, book_id="footnotes")

    footnotes = [b for b in _artifact_blocks(artifact.sections) if b.type == ReaderBlockType.FOOTNOTE]
    assert len(footnotes) == 4
    for i, block in enumerate(footnotes, start=1):
        assert block.source_page == i


def test_clean_table_caption_is_merged_into_the_table_block_not_a_sibling(storage: LocalDiskStorage):
    doc = _reconstruct("tables", storage)
    artifact = derive_reader_artifact(doc, book_id="tables")
    blocks = _artifact_blocks(artifact.sections)

    tables = [b for b in blocks if b.type == ReaderBlockType.TABLE]
    assert len(tables) == 2

    clean = next(t for t in tables if not t.preserve_as_image)
    assert clean.caption is not None
    assert "Participant summary" in clean.caption
    assert "John" in clean.content and "<table>" in clean.content

    # No orphaned caption block anywhere — it was fully absorbed.
    assert not any("Participant summary" in b.content for b in blocks if b is not clean)


def test_complex_table_stays_preserved_as_image_with_confidence_and_caption(storage: LocalDiskStorage):
    doc = _reconstruct("tables", storage)
    artifact = derive_reader_artifact(doc, book_id="tables")
    tables = [b for b in _artifact_blocks(artifact.sections) if b.type == ReaderBlockType.TABLE]

    messy = next(t for t in tables if t.preserve_as_image)
    assert messy.confidence < 0.9
    assert messy.asset_id is not None
    assert messy.content == ""


def test_equation_stays_preserved_as_image_asset(storage: LocalDiskStorage):
    doc = _reconstruct("equations", storage)
    artifact = derive_reader_artifact(doc, book_id="equations")
    blocks = _artifact_blocks(artifact.sections)

    equations = [b for b in blocks if b.type == ReaderBlockType.EQUATION]
    assert len(equations) == 1
    assert equations[0].preserve_as_image is True
    assert equations[0].asset_id is not None
    assert len(artifact.assets) == 1
    assert artifact.assets[0].id == equations[0].asset_id


def test_each_figure_caption_is_merged_into_its_own_figure_not_the_other(storage: LocalDiskStorage):
    doc = _reconstruct("figures_with_captions", storage)
    artifact = derive_reader_artifact(doc, book_id="figures_with_captions")
    blocks = _artifact_blocks(artifact.sections)

    figures = [b for b in blocks if b.type == ReaderBlockType.FIGURE]
    assert len(figures) == 2
    assert "Site A" in figures[0].caption
    assert "Site B" in figures[1].caption

    # The separating paragraph between the two figures survives untouched
    # and is not mistaken for anyone's caption.
    assert any("separates the two figures" in b.content for b in blocks)


def test_complex_visual_map_caption_is_merged(storage: LocalDiskStorage):
    doc = _reconstruct("complex_visual", storage)
    artifact = derive_reader_artifact(doc, book_id="complex_visual")
    figures = [b for b in _artifact_blocks(artifact.sections) if b.type == ReaderBlockType.FIGURE]

    assert len(figures) == 1
    assert figures[0].preserve_as_image is True
    assert figures[0].caption is not None
    assert "Survey regions" in figures[0].caption


def test_mixed_layout_reading_order_survives_derivation(storage: LocalDiskStorage):
    doc = _reconstruct("mixed_layout", storage)
    artifact = derive_reader_artifact(doc, book_id="mixed_layout")
    contents = [b.content for b in _artifact_blocks(artifact.sections)]

    def index_of(fragment: str) -> int:
        return next(i for i, c in enumerate(contents) if fragment in c)

    assert (
        index_of("introduces the topic")
        < index_of("stays on the left")
        < index_of("stays on the right")
        < index_of("summarizes the comparison")
        < index_of("returns to single-column")
    )


def test_three_column_order_and_content_survive_derivation(storage: LocalDiskStorage):
    doc = _reconstruct("three_column", storage)
    artifact = derive_reader_artifact(doc, book_id="three_column")
    contents = [b.content for b in _artifact_blocks(artifact.sections)]

    def index_of(fragment: str) -> int:
        return next(i for i, c in enumerate(contents) if fragment in c)

    assert index_of("Alpha section") < index_of("Beta section") < index_of("Gamma section")


def test_difficult_pdf_derives_without_error_and_validates(storage: LocalDiskStorage):
    from cozypdfs.reader_artifact.validation import validate as validate_artifact

    doc = _reconstruct("difficult", storage)
    artifact = derive_reader_artifact(doc, book_id="difficult")
    assert validate_artifact(artifact) == []


def test_realistic_book_excerpt_paragraph_order_and_text_survive(storage: LocalDiskStorage):
    doc = _reconstruct("realistic_book_excerpt", storage)
    artifact = derive_reader_artifact(doc, book_id="realistic_book_excerpt")
    contents = [b.content for b in _artifact_blocks(artifact.sections)]

    assert len(contents) == 4
    assert any("eleven winters" in c for c in contents)
    assert any("convinced herself it was nothing" in c for c in contents)


# ---------------------------------------------------------------------
# Multi-level heading -> nested section folding (synthetic DIR: no golden
# fixture currently has H2/H3 sub-headings to exercise this against).
# ---------------------------------------------------------------------


def _heading(id_: str, order: int, text: str, level: int) -> DIRBlock:
    return DIRBlock(id=id_, type=DIRBlockType.HEADING, order=order, content=f"<h{level}>{text}</h{level}>", level=level)


def _para(id_: str, order: int, text: str) -> DIRBlock:
    return DIRBlock(id=id_, type=DIRBlockType.PARAGRAPH, order=order, content=f"<p>{text}</p>")


def test_nested_headings_fold_into_a_matching_section_tree():
    blocks = [
        _para("b0", 0, "intro para"),
        _heading("b1", 1, "Section A", level=2),
        _para("b2", 2, "para under A"),
        _heading("b3", 3, "Subsection A1", level=3),
        _para("b4", 4, "para under A1"),
        _heading("b5", 5, "Section B", level=2),
        _para("b6", 6, "para under B"),
    ]
    chapter = DIRChapter(id="ch0", title="Chapter One", order=0, blocks=blocks)
    document = DIRDocument(meta=DIRMeta(title="T"), chapters=[chapter], assets=[])

    artifact = derive_reader_artifact(document, book_id="synthetic")
    assert len(artifact.sections) == 1
    root = artifact.sections[0]
    assert root.level == 1
    assert [b.content for b in root.blocks] == ["<p>intro para</p>"]

    assert len(root.children) == 2
    section_a, section_b = root.children
    assert section_a.title == "Section A" and section_a.level == 2
    assert [b.content for b in section_a.blocks] == ["<p>para under A</p>"]
    assert len(section_a.children) == 1
    assert section_a.children[0].title == "Subsection A1" and section_a.children[0].level == 3
    assert [b.content for b in section_a.children[0].blocks] == ["<p>para under A1</p>"]

    assert section_b.title == "Section B" and section_b.level == 2
    assert [b.content for b in section_b.blocks] == ["<p>para under B</p>"]
    assert section_b.children == []


def test_nested_section_navigation_mirrors_the_section_tree():
    blocks = [
        _heading("b0", 0, "Section A", level=2),
        _para("b1", 1, "para"),
    ]
    chapter = DIRChapter(id="ch0", title="Chapter One", order=0, blocks=blocks)
    document = DIRDocument(meta=DIRMeta(title="T"), chapters=[chapter], assets=[])

    artifact = derive_reader_artifact(document, book_id="synthetic")
    assert len(artifact.navigation) == 1
    top = artifact.navigation[0]
    assert top.title == "Chapter One"
    assert len(top.children) == 1
    assert top.children[0].title == "Section A"
    assert top.children[0].section_id == artifact.sections[0].children[0].id


def test_a_caption_with_no_preceding_figure_or_table_becomes_a_visible_orphan_paragraph():
    blocks = [DIRBlock(id="b0", type=DIRBlockType.CAPTION, order=0, content="<p>orphan caption</p>")]
    chapter = DIRChapter(id="ch0", title="Chapter One", order=0, blocks=blocks)
    document = DIRDocument(meta=DIRMeta(title="T"), chapters=[chapter], assets=[])

    artifact = derive_reader_artifact(document, book_id="synthetic")
    blocks_out = _artifact_blocks(artifact.sections)
    assert len(blocks_out) == 1
    assert blocks_out[0].type == ReaderBlockType.PARAGRAPH
    assert "orphan caption" in blocks_out[0].content


# ---------------------------------------------------------------------
# Semantic preservation: derivation is a pure re-shaping of DIR, not a
# reinterpretation. Representation may change; meaning must not.
# ---------------------------------------------------------------------

# Block types that are never their own artifact block: HEADING(level>=2) is
# promoted to a section title, and CAPTION is merged into its owning block.
_STRUCTURAL_TYPES = {DIRBlockType.CAPTION}


def _is_structural_heading(block: DIRBlock) -> bool:
    return block.type == DIRBlockType.HEADING and (block.level or 1) >= 2


def test_semantic_preservation_across_the_entire_golden_corpus(storage: LocalDiskStorage):
    for name in ALL_GOLDEN_NAMES:
        doc = _reconstruct(name, storage)
        artifact = derive_reader_artifact(doc, book_id=name)

        dir_blocks = [
            b
            for b in _dir_blocks(doc)
            if b.type not in _STRUCTURAL_TYPES and not _is_structural_heading(b)
        ]
        artifact_blocks = _artifact_blocks(artifact.sections)

        assert len(artifact_blocks) == len(dir_blocks), name

        for dir_block, reader_block in zip(dir_blocks, artifact_blocks, strict=True):
            assert reader_block.id == dir_block.id, name
            assert reader_block.type.value == dir_block.type.value, name
            assert reader_block.content == dir_block.content, name
            assert reader_block.confidence == dir_block.confidence, name
            assert reader_block.preserve_as_image == dir_block.preserve_as_image, name
            assert reader_block.asset_id == dir_block.asset_id, name
            assert reader_block.source_page == dir_block.source_page, name

        # Every DIR asset is still referenced by id from the artifact.
        assert {a.id for a in artifact.assets} == {a.id for a in doc.assets}, name


def test_derivation_is_deterministic(storage: LocalDiskStorage):
    doc = _reconstruct("mixed_layout", storage)
    first = derive_reader_artifact(doc, book_id="mixed_layout")
    second = derive_reader_artifact(doc, book_id="mixed_layout")
    assert first.model_dump() == second.model_dump()


def test_derivation_does_not_re_access_the_source_pdf(storage: LocalDiskStorage, monkeypatch):
    """A DIR-derived artifact must be reachable from the DIR alone — no
    hidden dependency on the original PDF bytes or any storage read beyond
    the DIRDocument object already in hand."""
    doc = _reconstruct("single_column_prose", storage)

    def _forbidden_get(*args, **kwargs):
        raise AssertionError("derive_reader_artifact must not read from storage")

    monkeypatch.setattr(storage, "get", _forbidden_get)
    derive_reader_artifact(doc, book_id="single_column_prose")
