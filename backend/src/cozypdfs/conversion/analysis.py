"""Stage: document analysis. An already-open PDF document -> per-page raw
spans/lines/images. This is the one stage that touches PyMuPDF's text/image
primitives directly — every later stage works off PageContent, not fitz
objects (the one exception is asset cropping, which legitimately needs to
re-render regions of the live document; see figures.py/tables.py/equations.py).

Deterministic: PyMuPDF's text extraction is a pure function of the PDF
bytes.
"""

import pymupdf

from cozypdfs.conversion.types import BBox, Line, PageContent, RawImage, Span

# PyMuPDF span flag bits (see pymupdf docs for TEXT_FONT_*).
_ITALIC = 2
_BOLD = 16


def analyze_document(doc: pymupdf.Document) -> list[PageContent]:
    return [_analyze_page(doc, index) for index in range(doc.page_count)]


def _analyze_page(doc: pymupdf.Document, index: int) -> PageContent:
    page = doc[index]
    page_number = index + 1
    raw = page.get_text("dict")

    lines: list[Line] = []
    images: list[RawImage] = []

    for block in raw["blocks"]:
        if block.get("type") == 1:
            images.append(
                RawImage(
                    bbox=BBox(*block["bbox"]),
                    page_number=page_number,
                    xref=block.get("number", -1),
                )
            )
            continue

        for raw_line in block.get("lines", []):
            spans = [
                Span(
                    text=span["text"],
                    size=span["size"],
                    font=span["font"],
                    bold=bool(span["flags"] & _BOLD),
                    italic=bool(span["flags"] & _ITALIC),
                    bbox=BBox(*span["bbox"]),
                )
                for span in raw_line["spans"]
                if span["text"].strip()
            ]
            if not spans:
                continue
            lines.append(Line(spans=spans, bbox=BBox(*raw_line["bbox"]), page_number=page_number))

    return PageContent(
        page_number=page_number,
        width=page.rect.width,
        height=page.rect.height,
        lines=lines,
        images=images,
    )
