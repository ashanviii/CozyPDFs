"""Semantic XHTML generation from a ReaderArtifact. One XHTML document per
top-level section (a DIR chapter); nested sub-sections become `<section>`
elements within it, per Phase 2B's requirement that navigation and content
share one structure.

Every block's content is DIR-derived semantic HTML already (see
conversion/assembly.py) and is embedded as-is — this stage never merges or
splits a paragraph, never reconstructs a table, never re-decides what's a
heading. Its only two jobs are: wrap a preserved visual block (and its
merged caption, if any) into a `<figure>`, and represent a footnote as a
semantic `<aside epub:type="footnote">`. Both are serialization choices
about content Phase 2A already decided, not new decisions about content.
"""

from html import escape

from cozypdfs.reader_artifact.schema import ReaderArtifact, ReaderBlock, ReaderSection

_XHTML_TEMPLATE = """<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
<title>{title}</title>
<link rel="stylesheet" type="text/css" href="{stylesheet_href}"/>
</head>
<body>
{body}
</body>
</html>
"""


def render_artifact_documents(artifact: ReaderArtifact, *, stylesheet_href: str = "style/style.css") -> dict[str, str]:
    """Returns {section_id: xhtml_document} — one document per top-level
    section, matching one EPUB spine entry each."""
    return {
        section.id: render_section_document(section, stylesheet_href=stylesheet_href)
        for section in artifact.sections
    }


def render_section_document(section: ReaderSection, *, stylesheet_href: str = "style/style.css") -> str:
    title = section.title or "Untitled"
    body = _render_section_body(section)
    return _XHTML_TEMPLATE.format(title=escape(title), stylesheet_href=stylesheet_href, body=body)


def _render_section_body(section: ReaderSection) -> str:
    parts: list[str] = []
    if section.title:
        level = min(max(section.level, 1), 6)
        parts.append(f"<h{level}>{escape(section.title)}</h{level}>")
    for block in section.blocks:
        parts.append(_render_block(block))
    for child in section.children:
        parts.append(f'<section id="{child.id}">')
        parts.append(_render_section_body(child))
        parts.append("</section>")
    return "\n".join(parts)


def _render_block(block: ReaderBlock) -> str:
    if block.preserve_as_image:
        return _render_figure(block)
    if block.type.value == "footnote":
        return _render_footnote(block)
    # PARAGRAPH/LIST/TABLE(reconstructed)/QUOTE/HEADING(defensive) already
    # carry valid semantic HTML from Phase 2A — embed as-is.
    return block.content


def _render_figure(block: ReaderBlock) -> str:
    alt = escape(block.caption or block.type.value)
    img = f'<img src="assets/{block.asset_id}.png" alt="{alt}"/>'
    caption = f"<figcaption>{escape(block.caption)}</figcaption>" if block.caption else ""
    return f'<figure id="{block.id}">{img}{caption}</figure>'


def _render_footnote(block: ReaderBlock) -> str:
    # block.content is already "<p>...</p>" — an aside is the semantic
    # EPUB3 wrapper; the paragraph inside is untouched.
    return f'<aside epub:type="footnote" id="{block.id}">{block.content}</aside>'
