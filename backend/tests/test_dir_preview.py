"""Tests for the developer visual-inspection HTML renderer — not
end-to-end golden output, but the specific rendering rules this tool
promises: no page-boundary markers in the content flow, provenance
confined to the gutter, assets embedded, low confidence visibly flagged
only when it's actually low.
"""

from cozypdfs.devtools.dir_preview import render_dir_preview
from cozypdfs.dir.schema import Asset, Block, BlockType, Chapter, DIRDocument, DIRMeta
from cozypdfs.storage.local import LocalDiskStorage


def _doc(*blocks: Block, assets: list[Asset] | None = None, title: str | None = "Chapter") -> DIRDocument:
    return DIRDocument(
        meta=DIRMeta(title="Test Book", author="An Author", language=None, source_type="pdf"),
        chapters=[Chapter(id="ch0", title=title, order=0, blocks=list(blocks))],
        assets=assets or [],
    )


def test_renders_paragraph_and_heading_content_directly(storage: LocalDiskStorage):
    doc = _doc(
        Block(id="b0", type=BlockType.HEADING, order=0, content="<h1>Intro</h1>", level=1),
        Block(id="b1", type=BlockType.PARAGRAPH, order=1, content="<p>Hello world.</p>"),
    )
    html = render_dir_preview(doc, storage)
    assert "<h1>Intro</h1>" in html
    assert "<p>Hello world.</p>" in html


def test_provenance_is_shown_but_not_inside_the_content_div(storage: LocalDiskStorage):
    doc = _doc(Block(id="b0", type=BlockType.PARAGRAPH, order=0, content="<p>Text.</p>", source_page=7))
    html = render_dir_preview(doc, storage)
    assert 'class="prov">p.7</span>' in html
    # The provenance marker lives in the .gutter div, not .content.
    gutter_start = html.index('class="gutter"')
    content_start = html.index('class="content"')
    prov_pos = html.index("p.7")
    assert gutter_start < prov_pos < content_start


def test_preserved_asset_is_embedded_as_a_data_uri(storage: LocalDiskStorage):
    storage.put("books/b/assets/asset-1.png", b"\x89PNG\r\n\x1a\nfakepngbytes")
    asset = Asset(id="asset-1", storage_key="books/b/assets/asset-1.png", width=100, height=80, alt_text="A figure")
    doc = _doc(
        Block(id="b0", type=BlockType.FIGURE, order=0, content="", preserve_as_image=True, asset_id="asset-1"),
        assets=[asset],
    )
    html = render_dir_preview(doc, storage)
    assert "data:image/png;base64," in html
    assert 'alt="A figure"' in html
    assert 'width="100"' in html and 'height="80"' in html


def test_low_confidence_asset_gets_a_visible_marker(storage: LocalDiskStorage):
    storage.put("books/b/assets/asset-1.png", b"pngbytes")
    asset = Asset(id="asset-1", storage_key="books/b/assets/asset-1.png")
    doc = _doc(
        Block(
            id="b0",
            type=BlockType.TABLE,
            order=0,
            content="",
            preserve_as_image=True,
            asset_id="asset-1",
            confidence=0.3,
        ),
        assets=[asset],
    )
    html = render_dir_preview(doc, storage)
    assert "block--low-confidence" in html
    assert "conf 0.3" in html


def test_high_confidence_asset_is_not_flagged_as_low_confidence(storage: LocalDiskStorage):
    storage.put("books/b/assets/asset-1.png", b"pngbytes")
    asset = Asset(id="asset-1", storage_key="books/b/assets/asset-1.png")
    doc = _doc(
        Block(
            id="b0",
            type=BlockType.FIGURE,
            order=0,
            content="",
            preserve_as_image=True,
            asset_id="asset-1",
            confidence=1.0,
        ),
        assets=[asset],
    )
    html = render_dir_preview(doc, storage)
    body = html[html.index("<main>") :]  # the CSS selector itself always appears in <style>
    assert "block--low-confidence" not in body


def test_missing_asset_degrades_gracefully_instead_of_raising(storage: LocalDiskStorage):
    doc = _doc(
        Block(id="b0", type=BlockType.FIGURE, order=0, content="", preserve_as_image=True, asset_id="does-not-exist")
    )
    html = render_dir_preview(doc, storage)
    assert "missing asset" in html


def test_chapter_title_renders_once_per_chapter(storage: LocalDiskStorage):
    doc = _doc(Block(id="b0", type=BlockType.PARAGRAPH, order=0, content="<p>Text.</p>"), title="Chapter One")
    html = render_dir_preview(doc, storage)
    assert html.count('class="chapter-title"') == 1
    assert "Chapter One" in html


def test_footnote_and_caption_get_distinct_styling_hooks(storage: LocalDiskStorage):
    doc = _doc(
        Block(id="b0", type=BlockType.FOOTNOTE, order=0, content="<p>A footnote.</p>"),
        Block(id="b1", type=BlockType.CAPTION, order=1, content="<figcaption>A caption.</figcaption>"),
    )
    html = render_dir_preview(doc, storage)
    assert "block--footnote" in html
    assert "block--caption" in html


def test_page_metadata_is_shown_in_the_header(storage: LocalDiskStorage):
    doc = _doc(Block(id="b0", type=BlockType.PARAGRAPH, order=0, content="<p>Text.</p>"))
    html = render_dir_preview(doc, storage)
    assert "Test Book" in html
    assert "An Author" in html
