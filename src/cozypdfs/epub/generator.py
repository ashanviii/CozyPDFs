"""Stage 7: EPUB generation.

Turns a `Book` -- the geometry-free semantic model -- into a standards
-compliant .epub. This is the one place PDF-derived facts turn into markup,
and the rule is strict: semantic types map to semantic HTML elements, full
stop. A `Paragraph` becomes `<p>`, a `Heading` becomes `<h1>`/`<h2>`, an
italic `Run` becomes `<em>`. Nothing here ever asks "what size was this
text in the PDF" -- the reader controls all of that through its own
stylesheet layered on top of the tiny, purely semantic CSS this stage
ships (a handful of class hooks, no fonts, no fixed sizes, no colors).

Uses `ebooklib` for EPUB packaging (manifest/spine/nav/NCX plumbing) and
`lxml` to build each chapter's XHTML as a real element tree -- text is
always assigned to `.text`/`.tail`, never concatenated into markup, so
content extracted from an untrusted PDF cannot inject markup into the
output.
"""

from __future__ import annotations

import posixpath
from pathlib import Path
from uuid import uuid4

from ebooklib import epub
from lxml import etree

from ..exceptions import EpubGenerationError
from ..models import (
    Block,
    Blockquote,
    Book,
    Chapter,
    ChapterKind,
    Epigraph,
    EquationBlock,
    Footnote,
    Heading,
    ImageBlock,
    ListBlock,
    Paragraph,
    ParagraphVariant,
    Poem,
    Run,
    SceneBreak,
    TableBlock,
)

_XHTML_NS = "http://www.w3.org/1999/xhtml"
_EPUB_OPS_NS = "http://www.idpf.org/2007/ops"

# Every chapter document lives at "text/{id}.xhtml" (set in `generate()`);
# any in-body reference to another manifest item (a stylesheet, an image)
# needs an href relative to *that* directory, not the OPF root.
_CHAPTER_DIR = "text"


def _relative_href(target: str) -> str:
    return posixpath.relpath(target, _CHAPTER_DIR)


def _image_src(image_paths: dict[str, str], asset_id: str) -> str:
    path = image_paths.get(asset_id)
    return _relative_href(path) if path else ""

_MIME_TO_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/bmp": "bmp",
    "image/webp": "webp",
}

# Intentionally minimal: semantic hooks only, no fonts/sizes/colors/margins.
# The reader owns every visual decision beyond these two.
_CSS = """\
.scene-break { text-align: center; }
.epigraph { font-style: italic; }
.footnote-marker { font-weight: bold; }
"""


class DefaultEpubGenerator:
    """`EpubGenerator` implementation backed by ebooklib + lxml."""

    def generate(self, book: Book, output_path: Path) -> Path:
        try:
            return self._generate(book, Path(output_path))
        except EpubGenerationError:
            raise
        except Exception as exc:
            raise EpubGenerationError(f"Failed to generate EPUB: {exc}") from exc

    def _generate(self, book: Book, output_path: Path) -> Path:
        epub_book = epub.EpubBook()
        epub_book.set_identifier(str(uuid4()))
        epub_book.set_title(book.metadata.title)
        epub_book.set_language(book.metadata.language)
        if book.metadata.author:
            epub_book.add_author(book.metadata.author)

        css_item = epub.EpubItem(
            uid="style", file_name="style/style.css", media_type="text/css",
            content=_CSS.encode("utf-8"),
        )
        epub_book.add_item(css_item)

        image_paths = _add_images(epub_book, book)

        if book.cover is not None:
            ext = _MIME_TO_EXT.get(book.cover.mime_type, "png")
            epub_book.set_cover(f"cover.{ext}", book.cover.data)

        html_items: list[tuple[Chapter, epub.EpubHtml]] = []
        for idx, chapter in enumerate(book.chapters, start=1):
            content = _render_chapter_xhtml(chapter, idx, image_paths)
            item = epub.EpubHtml(
                uid=chapter.id,
                file_name=f"text/{chapter.id}.xhtml",
                title=_chapter_label(chapter, idx),
                lang=book.metadata.language,
            )
            item.content = content
            # NOT item.add_item(css_item): EpubHtml.get_content() discards
            # whatever <link>/<meta> is in our own markup and rebuilds
            # <head> purely from this item's own `links` list -- and
            # add_item() computes that link's href as the CSS item's bare
            # manifest path ("style/style.css"), which is wrong once the
            # chapter itself lives under "text/" (it needs "../style/style.css").
            item.add_link(href=_relative_href(css_item.file_name), rel="stylesheet", type="text/css")
            epub_book.add_item(item)
            html_items.append((chapter, item))

        if not html_items:
            raise EpubGenerationError("Book has no chapters to generate.")

        epub_book.toc = tuple(
            item for chapter, item in html_items if chapter.kind != ChapterKind.FRONT_MATTER
        )
        epub_book.add_item(epub.EpubNcx())
        epub_book.add_item(epub.EpubNav())
        # "nav" is non-linear: it belongs in the spine/manifest for
        # structural completeness, but a reader opening the book fresh
        # should land on the first chapter, not the generated TOC page.
        epub_book.spine = [("nav", "no")] + [item for _, item in html_items]

        output_path.parent.mkdir(parents=True, exist_ok=True)
        epub.write_epub(str(output_path), epub_book)
        return output_path


def _add_images(epub_book: "epub.EpubBook", book: Book) -> dict[str, str]:
    """Register every image asset once; return asset id -> manifest href."""
    paths: dict[str, str] = {}
    for chapter in book.chapters:
        for block in chapter.blocks:
            asset = None
            if isinstance(block, ImageBlock):
                asset = block.asset
            elif isinstance(block, EquationBlock) and block.asset is not None:
                asset = block.asset
            if asset is None or asset.id in paths:
                continue
            ext = _MIME_TO_EXT.get(asset.mime_type, "png")
            file_name = f"images/{asset.id}.{ext}"
            epub_book.add_item(
                epub.EpubImage(
                    uid=f"img-{asset.id}",
                    file_name=file_name,
                    media_type=asset.mime_type,
                    content=asset.data,
                )
            )
            paths[asset.id] = file_name
    return paths


def _render_chapter_xhtml(chapter: Chapter, idx: int, image_paths: dict[str, str]) -> bytes:
    # Only <body> ends up in the EPUB: ebooklib's EpubHtml.get_content()
    # re-parses this document, keeps just its <body> children, and rebuilds
    # <head> itself from the EpubHtml item's own title/links/metas (set in
    # `generate()`). A <head> built here would be silently discarded, so
    # this only constructs an <html><body> shell to hold the real content.
    html = etree.Element(
        "{%s}html" % _XHTML_NS, nsmap={None: _XHTML_NS, "epub": _EPUB_OPS_NS}
    )
    body = etree.SubElement(html, "body")
    heading_text = _chapter_heading_text(chapter, idx)
    if heading_text and chapter.kind != ChapterKind.FRONT_MATTER:
        etree.SubElement(body, "h1").text = heading_text

    for block in chapter.blocks:
        _render_block(body, block, image_paths)

    return etree.tostring(
        html, pretty_print=True, xml_declaration=True, encoding="utf-8", doctype="<!DOCTYPE html>"
    )


def _render_block(body, block: Block, image_paths: dict[str, str]) -> None:
    if isinstance(block, Heading):
        level = min(max(block.level, 1), 6)
        _append_runs(etree.SubElement(body, f"h{level}"), block.runs)

    elif isinstance(block, Paragraph):
        p = etree.SubElement(body, "p")
        if block.variant != ParagraphVariant.NORMAL:
            p.set("class", block.variant.value)
        _append_runs(p, block.runs)

    elif isinstance(block, Blockquote):
        bq = etree.SubElement(body, "blockquote")
        _append_runs(etree.SubElement(bq, "p"), block.runs)
        if block.attribution:
            etree.SubElement(bq, "cite").text = block.attribution

    elif isinstance(block, Epigraph):
        div = etree.SubElement(body, "div")
        div.set("class", "epigraph")
        _append_runs(etree.SubElement(div, "p"), block.runs)
        if block.attribution:
            etree.SubElement(div, "cite").text = block.attribution

    elif isinstance(block, SceneBreak):
        p = etree.SubElement(body, "p")
        p.set("class", "scene-break")
        p.text = block.marker or "•"

    elif isinstance(block, Poem):
        div = etree.SubElement(body, "div")
        div.set("class", "poem")
        p = etree.SubElement(div, "p")
        for line_idx, line_runs in enumerate(block.lines):
            if line_idx > 0:
                etree.SubElement(p, "br")
            _append_runs(p, line_runs)
        if block.attribution:
            etree.SubElement(div, "cite").text = block.attribution

    elif isinstance(block, Footnote):
        aside = etree.SubElement(body, "aside")
        aside.set("{%s}type" % _EPUB_OPS_NS, "footnote")
        aside.set("id", f"fn-{block.marker}")
        p = etree.SubElement(aside, "p")
        etree.SubElement(p, "span", **{"class": "footnote-marker"}).text = f"{block.marker}. "
        _append_runs(p, block.runs)

    elif isinstance(block, ImageBlock):
        figure = etree.SubElement(body, "figure")
        img = etree.SubElement(figure, "img")
        img.set("src", _image_src(image_paths, block.asset.id))
        img.set("alt", block.alt_text)
        if block.caption:
            _append_runs(etree.SubElement(figure, "figcaption"), block.caption)

    elif isinstance(block, ListBlock):
        list_el = etree.SubElement(body, "ol" if block.ordered else "ul")
        for item_runs in block.items:
            _append_runs(etree.SubElement(list_el, "li"), item_runs)

    elif isinstance(block, TableBlock):
        table = etree.SubElement(body, "table")
        for row in block.rows:
            tr = etree.SubElement(table, "tr")
            for cell_runs in row:
                _append_runs(etree.SubElement(tr, "td"), cell_runs)

    elif isinstance(block, EquationBlock):
        _render_equation(body, block, image_paths)


def _render_equation(body, block: EquationBlock, image_paths: dict[str, str]) -> None:
    # Fidelity order per the architecture's rule: structured (MathML) >
    # visual preservation (image) > plain text (LaTeX source). Never
    # rewritten or approximated.
    if block.mathml:
        try:
            body.append(etree.fromstring(block.mathml.encode("utf-8")))
            return
        except etree.XMLSyntaxError:
            pass
    if block.asset is not None:
        figure = etree.SubElement(body, "figure")
        img = etree.SubElement(figure, "img")
        img.set("src", _image_src(image_paths, block.asset.id))
        img.set("alt", "equation")
        return
    if block.latex:
        p = etree.SubElement(body, "p")
        p.set("class", "equation-latex")
        p.text = block.latex


def _append_runs(parent, runs: list[Run]) -> None:
    """Append text runs, mapping semantic style flags to nested inline tags.

    Text is always set via `.text`/`.tail` on real elements -- never string
    -concatenated into markup -- so nothing extracted from the source PDF
    can be interpreted as HTML.
    """
    for run in runs:
        if not run.text:
            continue
        if run.footnote_ref:
            sup = etree.SubElement(parent, "sup")
            link = etree.SubElement(sup, "a")
            link.set("{%s}type" % _EPUB_OPS_NS, "noteref")
            link.set("href", f"#fn-{run.footnote_ref}")
            link.text = run.text
            continue
        container = parent
        wrapper = None
        if run.bold:
            wrapper = etree.SubElement(container, "strong")
            container = wrapper
        if run.italic:
            el = etree.SubElement(container, "em")
            wrapper = wrapper if wrapper is not None else el
            container = el
        if run.superscript:
            el = etree.SubElement(container, "sup")
            wrapper = wrapper if wrapper is not None else el
            container = el
        if run.subscript:
            el = etree.SubElement(container, "sub")
            wrapper = wrapper if wrapper is not None else el
            container = el

        if wrapper is None:
            _append_text(parent, run.text)
        else:
            container.text = (container.text or "") + run.text


def _append_text(parent, text: str) -> None:
    children = list(parent)
    if children:
        children[-1].tail = (children[-1].tail or "") + text
    else:
        parent.text = (parent.text or "") + text


def _chapter_heading_text(chapter: Chapter, idx: int) -> str | None:
    if chapter.kind == ChapterKind.FRONT_MATTER:
        return None
    if chapter.kind == ChapterKind.PROLOGUE:
        return chapter.title or "Prologue"
    if chapter.kind == ChapterKind.EPILOGUE:
        return chapter.title or "Epilogue"
    if chapter.number and chapter.title:
        return f"Chapter {chapter.number}: {chapter.title}"
    if chapter.number:
        return f"Chapter {chapter.number}"
    if chapter.title:
        return chapter.title
    return f"Chapter {idx}"


def _chapter_label(chapter: Chapter, idx: int) -> str:
    return _chapter_heading_text(chapter, idx) or f"Chapter {idx}"
