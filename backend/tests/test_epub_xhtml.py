"""Semantic XHTML generation from a ReaderArtifact section tree: proper
elements (hN, figure/figcaption, aside for footnotes), no arbitrary line
breaks, nested sections become nested <section> elements."""

from cozypdfs.epub.xhtml import render_section_document
from cozypdfs.reader_artifact.schema import ReaderBlock, ReaderBlockType, ReaderSection


def _para(id_: str, order: int, content: str) -> ReaderBlock:
    return ReaderBlock(id=id_, type=ReaderBlockType.PARAGRAPH, order=order, content=content)


def test_section_title_renders_as_a_heading_matching_its_level():
    section = ReaderSection(id="s1", title="Chapter One", level=1, blocks=[])
    html = render_section_document(section)
    assert "<h1>Chapter One</h1>" in html


def test_nested_subsection_title_renders_at_its_own_level():
    child = ReaderSection(id="child", title="Section A", level=2, blocks=[_para("b1", 0, "<p>x</p>")])
    root = ReaderSection(id="root", title="Chapter One", level=1, blocks=[], children=[child])
    html = render_section_document(root)
    assert "<h2>Section A</h2>" in html


def test_nested_subsection_is_wrapped_in_a_section_element_with_its_own_id():
    child = ReaderSection(id="child-id", title="Section A", level=2, blocks=[])
    root = ReaderSection(id="root", title="Chapter One", level=1, blocks=[], children=[child])
    html = render_section_document(root)
    assert '<section id="child-id">' in html
    assert html.count("</section>") == 1


def test_paragraph_content_is_passed_through_as_its_own_html():
    section = ReaderSection(id="s1", title=None, level=1, blocks=[_para("b1", 0, "<p>Hello world.</p>")])
    html = render_section_document(section)
    assert "<p>Hello world.</p>" in html


def test_list_content_is_passed_through_as_real_list_markup():
    block = ReaderBlock(id="b1", type=ReaderBlockType.LIST, order=0, content="<ul><li>one</li><li>two</li></ul>")
    section = ReaderSection(id="s1", title=None, level=1, blocks=[block])
    html = render_section_document(section)
    assert "<ul><li>one</li><li>two</li></ul>" in html


def test_table_content_is_passed_through_as_real_table_markup():
    block = ReaderBlock(id="b1", type=ReaderBlockType.TABLE, order=0, content="<table><tr><td>x</td></tr></table>")
    section = ReaderSection(id="s1", title=None, level=1, blocks=[block])
    html = render_section_document(section)
    assert "<table><tr><td>x</td></tr></table>" in html


def test_footnote_renders_as_an_aside_with_epub_footnote_type():
    block = ReaderBlock(id="fn1", type=ReaderBlockType.FOOTNOTE, order=0, content="<p>See appendix.</p>")
    section = ReaderSection(id="s1", title=None, level=1, blocks=[block])
    html = render_section_document(section)
    assert '<aside epub:type="footnote" id="fn1">' in html
    assert "See appendix." in html


def test_preserved_image_block_renders_as_figure_with_img_and_caption():
    block = ReaderBlock(
        id="fig1",
        type=ReaderBlockType.FIGURE,
        order=0,
        content="",
        preserve_as_image=True,
        asset_id="asset-1",
        caption="Figure 1: a diagram",
    )
    section = ReaderSection(id="s1", title=None, level=1, blocks=[block])
    html = render_section_document(section)
    assert '<figure id="fig1">' in html
    assert '<img src="assets/asset-1.png"' in html
    assert "<figcaption>Figure 1: a diagram</figcaption>" in html


def test_preserved_image_without_a_caption_renders_no_figcaption():
    block = ReaderBlock(
        id="fig1", type=ReaderBlockType.FIGURE, order=0, content="", preserve_as_image=True, asset_id="asset-1"
    )
    section = ReaderSection(id="s1", title=None, level=1, blocks=[block])
    html = render_section_document(section)
    assert "<figcaption>" not in html


def test_special_characters_in_a_title_are_escaped():
    section = ReaderSection(id="s1", title="Q&A <notes>", level=1, blocks=[])
    html = render_section_document(section)
    assert "Q&amp;A &lt;notes&gt;" in html
    assert "<notes>" not in html


def test_document_includes_stylesheet_link_and_xhtml_doctype():
    section = ReaderSection(id="s1", title="T", level=1, blocks=[])
    html = render_section_document(section, stylesheet_href="style/style.css")
    assert '<link rel="stylesheet" type="text/css" href="style/style.css"/>' in html
    assert 'xmlns="http://www.w3.org/1999/xhtml"' in html
    assert 'xmlns:epub="http://www.idpf.org/2007/ops"' in html


def test_blocks_render_before_nested_children_in_document_order():
    child = ReaderSection(id="child", title="Sub", level=2, blocks=[_para("b2", 1, "<p>child para</p>")])
    root = ReaderSection(
        id="root", title="Root", level=1, blocks=[_para("b1", 0, "<p>root para</p>")], children=[child]
    )
    html = render_section_document(root)
    assert html.index("root para") < html.index("Sub") < html.index("child para")
