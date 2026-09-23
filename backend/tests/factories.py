import pymupdf


def make_pdf_bytes(pages: int = 1, title: str | None = None, author: str | None = None) -> bytes:
    doc = pymupdf.open()
    try:
        for _ in range(pages):
            doc.new_page()
        if title or author:
            doc.set_metadata({"title": title or "", "author": author or ""})
        return doc.tobytes()
    finally:
        doc.close()
