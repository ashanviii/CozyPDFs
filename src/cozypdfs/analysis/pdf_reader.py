"""Stage 1: PDF analysis.

Turns a PDF file into a `RawDocument` -- a faithful, geometry-aware
transcription of every page's text spans, lines, blocks, images, and font
attributes. This stage makes no judgments about structure: it does not
decide what is a heading, a header, or a paragraph. It only answers "what
is physically on this page, and where."

Uses PyMuPDF (`fitz`), which exposes exactly the per-span font name, size,
and style flags this reconstruction pipeline depends on -- most PDF text
extractors only give flat strings.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf as fitz

from ..exceptions import EmptyDocumentError, PdfAnalysisError
from ..models import (
    BBox,
    RawBlock,
    RawBlockType,
    RawDocument,
    RawImageData,
    RawLine,
    RawPage,
    RawSpan,
)

# PyMuPDF span flag bits (see pymupdf docs for `flags`).
_FLAG_SUPERSCRIPT = 1 << 0
_FLAG_ITALIC = 1 << 1
_FLAG_BOLD = 1 << 4

# Hard safety ceiling: a novel is a few hundred pages. Refuse absurdly large
# inputs rather than trying to hold an unbounded document in memory.
_MAX_PAGES = 5000


class PyMuPdfAnalyzer:
    """`PdfAnalyzer` implementation backed by PyMuPDF."""

    def analyze(self, pdf_path: Path) -> RawDocument:
        pdf_path = Path(pdf_path)
        try:
            doc = fitz.open(pdf_path)
        except Exception as exc:  # PyMuPDF raises various internal error types
            raise PdfAnalysisError(f"Could not open PDF: {exc}") from exc

        try:
            if doc.is_encrypted and not doc.authenticate(""):
                raise PdfAnalysisError("PDF is password-protected.")

            page_count = doc.page_count
            if page_count == 0:
                raise EmptyDocumentError("PDF has no pages.")
            if page_count > _MAX_PAGES:
                raise PdfAnalysisError(
                    f"PDF has {page_count} pages, exceeding the {_MAX_PAGES} page limit."
                )

            pages = [self._read_page(doc, i) for i in range(page_count)]
        except PdfAnalysisError:
            raise
        except Exception as exc:
            raise PdfAnalysisError(f"Failed while reading PDF content: {exc}") from exc
        finally:
            doc.close()

        return RawDocument(source_path=pdf_path, page_count=page_count, pages=pages)

    def _read_page(self, doc: "fitz.Document", index: int) -> RawPage:
        page = doc[index]
        raw = page.get_text("dict")
        blocks: list[RawBlock] = []

        for block in raw.get("blocks", []):
            btype = block.get("type", 0)
            bbox = _to_bbox(block["bbox"])

            if btype == 1:
                image = _extract_image(block)
                if image is not None:
                    blocks.append(
                        RawBlock(bbox=bbox, block_type=RawBlockType.IMAGE, image=image)
                    )
                continue

            lines = [self._read_line(line) for line in block.get("lines", [])]
            lines = [ln for ln in lines if ln.spans]
            if lines:
                blocks.append(
                    RawBlock(bbox=bbox, block_type=RawBlockType.TEXT, lines=lines)
                )

        return RawPage(index=index, width=page.rect.width, height=page.rect.height, blocks=blocks)

    def _read_line(self, line: dict) -> RawLine:
        spans: list[RawSpan] = []
        for span in line.get("spans", []):
            text = span.get("text", "")
            if not text:
                continue
            flags = span.get("flags", 0)
            font_name = span.get("font", "")
            spans.append(
                RawSpan(
                    text=text,
                    bbox=_to_bbox(span["bbox"]),
                    font_name=font_name,
                    font_size=float(span.get("size", 0.0)),
                    italic=_is_italic(flags, font_name),
                    bold=_is_bold(flags, font_name),
                    superscript=bool(flags & _FLAG_SUPERSCRIPT),
                    color=span.get("color", 0),
                )
            )
        return RawLine(bbox=_to_bbox(line["bbox"]), spans=spans)


def _to_bbox(coords: list[float] | tuple[float, ...]) -> BBox:
    x0, y0, x1, y1 = coords
    return BBox(x0=x0, y0=y0, x1=x1, y1=y1)


def _is_italic(flags: int, font_name: str) -> bool:
    if flags & _FLAG_ITALIC:
        return True
    lname = font_name.lower()
    return "italic" in lname or "oblique" in lname


def _is_bold(flags: int, font_name: str) -> bool:
    if flags & _FLAG_BOLD:
        return True
    return "bold" in font_name.lower()


def _extract_image(block: dict) -> RawImageData | None:
    data = block.get("image")
    if not data:
        return None
    ext = block.get("ext", "png")
    return RawImageData(
        bbox=_to_bbox(block["bbox"]),
        data=data,
        mime_type=f"image/{ 'jpeg' if ext in ('jpg', 'jpeg') else ext }",
        width=int(block.get("width", 0)),
        height=int(block.get("height", 0)),
    )
