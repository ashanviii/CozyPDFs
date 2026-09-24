"""Structural validation of ReaderArtifact. Positive tests alone would not
prove the validator catches anything — these are deliberately-broken
artifacts, one invariant at a time, asserting the validator actually flags
each one (and only that one where practical)."""

import pytest

from cozypdfs.reader_artifact.schema import (
    NavigationItem,
    ReaderArtifact,
    ReaderAsset,
    ReaderBlock,
    ReaderBlockType,
    ReaderMeta,
    ReaderSection,
)
from cozypdfs.reader_artifact.validation import (
    ReaderArtifactValidationError,
    validate,
    validate_or_raise,
)


def _artifact(sections=None, assets=None, navigation=None) -> ReaderArtifact:
    return ReaderArtifact(
        book_id="b1",
        dir_schema_version=2,
        meta=ReaderMeta(title="T"),
        sections=sections or [],
        assets=assets or [],
        navigation=navigation or [],
    )


def _para(id_: str, order: int, content: str = "<p>x</p>") -> ReaderBlock:
    return ReaderBlock(id=id_, type=ReaderBlockType.PARAGRAPH, order=order, content=content)


def test_valid_artifact_has_no_issues():
    section = ReaderSection(id="s1", title="Ch1", level=1, blocks=[_para("b1", 0)])
    artifact = _artifact(sections=[section], navigation=[NavigationItem(section_id="s1", title="Ch1", level=1)])
    assert validate(artifact) == []


def test_empty_artifact_has_no_sections_is_flagged():
    issues = validate(_artifact(sections=[]))
    assert any("no sections" in i.message for i in issues)


def test_duplicate_section_id_is_flagged():
    s1 = ReaderSection(id="dup", title="A", level=1, blocks=[_para("b1", 0)])
    s2 = ReaderSection(id="dup", title="B", level=1, blocks=[_para("b2", 0)])
    issues = validate(_artifact(sections=[s1, s2]))
    assert any("duplicate section id" in i.message for i in issues)


def test_duplicate_block_id_is_flagged():
    section = ReaderSection(id="s1", title="A", level=1, blocks=[_para("b1", 0), _para("b1", 1)])
    issues = validate(_artifact(sections=[section]))
    assert any("duplicate block id" in i.message for i in issues)


def test_duplicate_block_id_across_sections_is_flagged():
    s1 = ReaderSection(id="s1", title="A", level=1, blocks=[_para("shared", 0)])
    s2 = ReaderSection(id="s2", title="B", level=1, blocks=[_para("shared", 0)])
    issues = validate(_artifact(sections=[s1, s2]))
    assert any("duplicate block id" in i.message for i in issues)


def test_out_of_order_blocks_are_flagged():
    section = ReaderSection(id="s1", title="A", level=1, blocks=[_para("b1", 5), _para("b2", 1)])
    issues = validate(_artifact(sections=[section]))
    assert any("out of order" in i.message for i in issues)


def test_out_of_range_confidence_is_flagged():
    block = _para("b1", 0)
    block.confidence = 1.5
    section = ReaderSection(id="s1", title="A", level=1, blocks=[block])
    issues = validate(_artifact(sections=[section]))
    assert any("out-of-range confidence" in i.message for i in issues)


def test_negative_confidence_is_flagged():
    block = _para("b1", 0)
    block.confidence = -0.1
    section = ReaderSection(id="s1", title="A", level=1, blocks=[block])
    issues = validate(_artifact(sections=[section]))
    assert any("out-of-range confidence" in i.message for i in issues)


def test_block_referencing_missing_asset_is_flagged():
    block = ReaderBlock(
        id="b1", type=ReaderBlockType.FIGURE, order=0, content="", preserve_as_image=True, asset_id="ghost"
    )
    section = ReaderSection(id="s1", title="A", level=1, blocks=[block])
    issues = validate(_artifact(sections=[section], assets=[]))
    assert any("missing asset" in i.message for i in issues)


def test_preserve_as_image_without_asset_id_is_flagged():
    block = ReaderBlock(id="b1", type=ReaderBlockType.FIGURE, order=0, content="", preserve_as_image=True)
    section = ReaderSection(id="s1", title="A", level=1, blocks=[block])
    issues = validate(_artifact(sections=[section]))
    assert any("without an asset_id" in i.message for i in issues)


def test_table_block_without_table_markup_is_flagged():
    block = ReaderBlock(id="b1", type=ReaderBlockType.TABLE, order=0, content="<p>not a table</p>")
    section = ReaderSection(id="s1", title="A", level=1, blocks=[block])
    issues = validate(_artifact(sections=[section]))
    assert any("no <table> content" in i.message for i in issues)


def test_table_block_preserved_as_image_is_exempt_from_table_markup_check():
    asset = ReaderAsset(id="a1", filename="a1.png", media_type="image/png")
    block = ReaderBlock(
        id="b1", type=ReaderBlockType.TABLE, order=0, content="", preserve_as_image=True, asset_id="a1"
    )
    section = ReaderSection(id="s1", title="A", level=1, blocks=[block])
    issues = validate(_artifact(sections=[section], assets=[asset]))
    assert issues == []


def test_empty_content_non_preserved_block_is_flagged():
    block = ReaderBlock(id="b1", type=ReaderBlockType.PARAGRAPH, order=0, content="   ")
    section = ReaderSection(id="s1", title="A", level=1, blocks=[block])
    issues = validate(_artifact(sections=[section]))
    assert any("has no content" in i.message for i in issues)


def test_navigation_referencing_missing_section_is_flagged():
    section = ReaderSection(id="s1", title="A", level=1, blocks=[_para("b1", 0)])
    nav = NavigationItem(section_id="ghost", title="A", level=1)
    issues = validate(_artifact(sections=[section], navigation=[nav]))
    assert any("missing section" in i.message for i in issues)


def test_nested_section_blocks_are_walked_and_validated():
    child = ReaderSection(id="child", title="C", level=2, blocks=[_para("b1", 5), _para("b2", 1)])
    root = ReaderSection(id="root", title="R", level=1, blocks=[], children=[child])
    issues = validate(_artifact(sections=[root]))
    assert any("out of order" in i.message for i in issues)


def test_nested_navigation_children_are_walked():
    section = ReaderSection(id="s1", title="A", level=1, blocks=[_para("b1", 0)])
    nav = NavigationItem(section_id="s1", title="A", level=1, children=[NavigationItem(section_id="ghost", title="B", level=2)])
    issues = validate(_artifact(sections=[section], navigation=[nav]))
    assert any("missing section" in i.message for i in issues)


def test_validate_or_raise_raises_on_issues():
    with pytest.raises(ReaderArtifactValidationError):
        validate_or_raise(_artifact(sections=[]))


def test_validate_or_raise_does_not_raise_on_a_valid_artifact():
    section = ReaderSection(id="s1", title="A", level=1, blocks=[_para("b1", 0)])
    validate_or_raise(_artifact(sections=[section]))
