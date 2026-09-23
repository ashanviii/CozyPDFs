"""Focused unit tests for the trickiest pure-logic pieces of the
conversion pipeline — the parts the golden-output tests exercise only
indirectly (nested lists, the validator's individual checks) or that
deserve a direct, minimal repro of a specific rule (paragraph
continuation, equation-token detection)."""

from cozypdfs.conversion import layout, lists, paragraphs, validation
from cozypdfs.conversion.classify import _is_math_token, _looks_like_equation
from cozypdfs.conversion.types import BBox, ClassifiedLine, Line, LineRole, Span
from cozypdfs.dir.schema import Asset, Block, BlockType, Chapter, DIRDocument, DIRMeta


def _line(text: str, x0: float, y0: float, y1: float, page: int = 1, size: float = 10.0) -> ClassifiedLine:
    span = Span(text=text, size=size, font="Helvetica", bold=False, italic=False, bbox=BBox(x0, y0, x0 + 50, y1))
    line = Line(spans=[span], bbox=BBox(x0, y0, x0 + 50, y1), page_number=page)
    return ClassifiedLine(line=line, role=LineRole.BODY)


def _raw_line(x0: float, x1: float, y0: float = 100.0, y1: float = 112.0, page: int = 1) -> Line:
    span = Span(text="x" * 10, size=10.0, font="Helvetica", bold=False, italic=False, bbox=BBox(x0, y0, x1, y1))
    return Line(spans=[span], bbox=BBox(x0, y0, x1, y1), page_number=page)


# --- paragraphs.is_continuation -----------------------------------------


def test_is_continuation_true_for_normal_line_wrap():
    prev = _line("first line", 50, 100, 112)
    curr = _line("second line", 50, 113, 125)
    assert paragraphs.is_continuation(prev, curr, typical_gap=1.0) is True


def test_is_continuation_false_for_large_gap():
    prev = _line("end of paragraph.", 50, 100, 112)
    curr = _line("Start of a new one.", 50, 140, 152)
    assert paragraphs.is_continuation(prev, curr, typical_gap=1.0) is False


def test_is_continuation_false_for_indent_jump():
    prev = _line("normal line", 50, 100, 112)
    curr = _line("a heading-like indented line", 150, 113, 125)
    assert paragraphs.is_continuation(prev, curr, typical_gap=1.0) is False


def test_is_continuation_true_across_page_when_sentence_unfinished():
    prev = _line("this sentence continues", 50, 550, 562, page=1)
    curr = _line("onto the next page", 50, 50, 62, page=2)
    assert paragraphs.is_continuation(prev, curr, typical_gap=1.0) is True


def test_is_continuation_false_across_page_when_sentence_finished():
    prev = _line("this sentence is done.", 50, 550, 562, page=1)
    curr = _line("A new one starts here.", 50, 50, 62, page=2)
    assert paragraphs.is_continuation(prev, curr, typical_gap=1.0) is False


# --- paragraphs.join_text -------------------------------------------------


def test_join_text_dehyphenates_a_word_split_across_lines():
    lines = [_line("This is a hyphen-", 50, 100, 112), _line("ated word.", 50, 113, 125)]
    assert paragraphs.join_text(lines) == "This is a hyphenated word."


def test_join_text_keeps_a_real_dash_when_next_word_is_capitalized():
    # Capitalized continuation is not treated as mid-word hyphenation, so
    # the hyphen and the normal space join are both preserved.
    lines = [_line("A well-", 50, 100, 112), _line("Known Author wrote this.", 50, 113, 125)]
    assert paragraphs.join_text(lines) == "A well- Known Author wrote this."


def test_join_text_joins_normal_lines_with_a_space():
    lines = [_line("Hello", 50, 100, 112), _line("world.", 50, 113, 125)]
    assert paragraphs.join_text(lines) == "Hello world."


# --- lists.build_list_html -----------------------------------------------


def _list_item(text: str, marker: str, indent: float) -> ClassifiedLine:
    cl = _line(text, indent, 100, 112)
    cl.role = LineRole.LIST_ITEM
    cl.list_marker = marker
    cl.list_indent = indent
    return cl


def test_build_list_html_flat_unordered_list():
    items = [_list_item("- first", "-", 50), _list_item("- second", "-", 50)]
    html = lists.build_list_html(items)
    assert html == "<ul><li>first</li><li>second</li></ul>"


def test_build_list_html_ordered_list_detects_numeric_markers():
    items = [_list_item("1. one", "1.", 50), _list_item("2. two", "2.", 50)]
    html = lists.build_list_html(items)
    assert html.startswith("<ol>")
    assert "<li>one</li>" in html


def test_build_list_html_nests_deeper_indented_items():
    items = [
        _list_item("- top", "-", 50),
        _list_item("- nested", "-", 62),  # one indent step deeper
        _list_item("- back to top", "-", 50),
    ]
    html = lists.build_list_html(items)
    assert html == "<ul><li>top<ul><li>nested</li></ul></li><li>back to top</li></ul>"


# --- classify: equation token detection -----------------------------------


def test_looks_like_equation_for_ascii_algebra():
    assert _looks_like_equation("x^2 + y^2 = z^2") is True


def test_does_not_flag_ordinary_sentence_with_a_couple_of_numbers():
    assert _looks_like_equation("In 1995 the team published 2 papers.") is False


def test_is_math_token_requires_a_digit_for_variable_pattern():
    assert _is_math_token("x2") is True
    assert _is_math_token("a") is False  # bare single letter — too common in prose to count


def test_is_math_token_recognizes_pure_operator_tokens():
    assert _is_math_token("=") is True
    assert _is_math_token("+") is True
    assert _is_math_token("the") is False


# --- validation ------------------------------------------------------------


def _valid_document() -> DIRDocument:
    return DIRDocument(
        meta=DIRMeta(title="T", author="A", language=None, source_type="pdf"),
        chapters=[
            Chapter(
                id="ch0",
                title=None,
                order=0,
                blocks=[Block(id="b0", type=BlockType.PARAGRAPH, order=0, content="<p>hello</p>")],
            )
        ],
        assets=[],
    )


def test_validate_accepts_a_well_formed_document():
    assert validation.validate(_valid_document()) == []


def test_validate_flags_out_of_range_confidence():
    doc = _valid_document()
    doc.chapters[0].blocks[0].confidence = 1.5
    issues = validation.validate(doc)
    assert any("confidence" in i.message for i in issues)


def test_validate_flags_missing_asset_reference():
    doc = _valid_document()
    doc.chapters[0].blocks[0].asset_id = "does-not-exist"
    issues = validation.validate(doc)
    assert any("missing asset" in i.message for i in issues)


def test_validate_flags_preserve_as_image_without_asset_id():
    doc = _valid_document()
    doc.chapters[0].blocks[0].preserve_as_image = True
    doc.chapters[0].blocks[0].asset_id = None
    issues = validation.validate(doc)
    assert any("no asset_id" in i.message for i in issues)


def test_validate_allows_empty_content_when_preserved_as_image():
    doc = _valid_document()
    doc.chapters[0].blocks[0].preserve_as_image = True
    doc.chapters[0].blocks[0].content = ""
    doc.chapters[0].blocks[0].asset_id = "asset-1"
    doc.assets = [Asset(id="asset-1", storage_key="k", width=1, height=1)]
    assert validation.validate(doc) == []


def test_validate_flags_empty_content_when_not_preserved():
    doc = _valid_document()
    doc.chapters[0].blocks[0].content = ""
    issues = validation.validate(doc)
    assert any("no content" in i.message for i in issues)


def test_validate_flags_duplicate_block_ids():
    doc = _valid_document()
    doc.chapters[0].blocks.append(
        Block(id="b0", type=BlockType.PARAGRAPH, order=1, content="<p>again</p>")
    )
    issues = validation.validate(doc)
    assert any("duplicate block id" in i.message for i in issues)


def test_validate_flags_a_document_with_no_chapters():
    doc = _valid_document()
    doc.chapters = []
    issues = validation.validate(doc)
    assert any("no chapters" in i.message for i in issues)


def test_validate_or_raise_raises_on_issues():
    doc = _valid_document()
    doc.chapters = []
    try:
        validation.validate_or_raise(doc)
        raised = False
    except validation.DIRValidationError:
        raised = True
    assert raised


# --- layout: N-column detection --------------------------------------------


def _column(x0: float, x1: float, n_lines: int = 4, page_width: float = 400.0) -> list[Line]:
    """n_lines evenly spaced lines within one column band."""
    return [_raw_line(x0, x1, y0=100.0 + i * 15, y1=100.0 + i * 15 + 12) for i in range(n_lines)]


def test_detect_columns_single_column_stays_full_width():
    lines = [_raw_line(50, 350, y0=100 + i * 15, y1=100 + i * 15 + 12) for i in range(6)]
    bands = layout._detect_columns(lines, page_width=400.0)
    assert bands == [layout.ColumnBand(0.0, 400.0)]


def test_detect_columns_finds_two_columns():
    lines = _column(50, 180) + _column(220, 350)
    bands = layout._detect_columns(lines, page_width=400.0)
    assert len(bands) == 2
    assert bands[0].x1 < bands[1].x0


def test_detect_columns_finds_three_columns_of_equal_width():
    lines = _column(20, 130) + _column(150, 260) + _column(280, 390)
    bands = layout._detect_columns(lines, page_width=400.0)
    assert len(bands) == 3


def test_detect_columns_tolerates_uneven_widths_and_content():
    lines = _column(20, 80, n_lines=2) + _column(100, 300, n_lines=5) + _column(320, 390, n_lines=3)
    bands = layout._detect_columns(lines, page_width=400.0)
    assert len(bands) == 3


def test_detect_columns_falls_back_on_ambiguous_three_way_split():
    """Three columns that don't cleanly separate (heavy overlap / no
    consistent gutter) must fall back to single-flow, never a confidently
    wrong split."""
    lines = [
        _raw_line(20, 150, y0=100, y1=112),
        _raw_line(130, 260, y0=115, y1=127),
        _raw_line(240, 390, y0=130, y1=142),
        _raw_line(20, 150, y0=145, y1=157),
    ]
    bands = layout._detect_columns(lines, page_width=400.0)
    assert bands == [layout.ColumnBand(0.0, 400.0)]


def test_detect_columns_a_heading_bridging_a_gutter_does_not_hide_it():
    heading = _raw_line(20, 250, y0=50, y1=65)  # wide, spans across the gutter
    lines = [heading] + _column(20, 120) + _column(180, 380)
    bands = layout._detect_columns(lines, page_width=400.0)
    assert len(bands) == 2


def test_detect_columns_a_columns_own_widest_line_is_not_mistaken_for_bridging():
    # One column's widest line reaches further than its siblings, right up
    # to the edge of a real gutter -- it must stay assigned to its column,
    # not get excluded as if it were bridging.
    left = _column(20, 120, n_lines=3) + [_raw_line(20, 140, y0=145, y1=157)]
    right = _column(180, 380, n_lines=4)
    bands = layout._detect_columns(left + right, page_width=400.0)
    assert len(bands) == 2
    assert bands[0].x1 >= 140  # the widest left-column line's own extent is preserved


def test_find_bridging_lines_identifies_the_specific_bridging_line():
    heading = _raw_line(20, 250, y0=50, y1=65)
    candidates = [heading] + _column(20, 120) + _column(180, 380)
    bridging = layout._find_bridging_lines(candidates)
    assert bridging == {id(heading)}
