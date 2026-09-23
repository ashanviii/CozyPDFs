"""PDF-format validation and metadata extraction — the "document analysis"
half of PDF ingestion (see the architecture's pipeline-stage breakdown).
Deliberately narrow: this module only answers "is this a real PDF, and how
many pages/what metadata does it have", not anything about layout or
content, which belongs to the (not yet built) conversion pipeline.
"""

from dataclasses import dataclass

import pymupdf

from cozypdfs.domain.errors import ValidationError

PDF_MAGIC = b"%PDF-"


class InvalidPDFError(ValidationError):
    pass


@dataclass
class PDFInfo:
    page_count: int
    title: str | None
    author: str | None


def has_pdf_magic_bytes(data: bytes) -> bool:
    """Real file-content inspection, not a filename/content-type check —
    PDFs start with `%PDF-` (occasionally after a few bytes of leading
    junk some producers add)."""
    return PDF_MAGIC in data[:1024]


def extract_pdf_info(data: bytes) -> PDFInfo:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise InvalidPDFError("could not open file as a PDF") from exc

    try:
        if doc.page_count < 1:
            raise InvalidPDFError("PDF has no pages")
        meta = doc.metadata or {}
        title = (meta.get("title") or "").strip() or None
        author = (meta.get("author") or "").strip() or None
        return PDFInfo(page_count=doc.page_count, title=title, author=author)
    finally:
        doc.close()
