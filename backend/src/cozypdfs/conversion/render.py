"""Shared PDF-region-to-PNG rendering. Used by every stage that preserves
content visually instead of reconstructing it (tables, equations, figures)
— one place doing the actual pixmap rendering rather than three."""

import pymupdf

from cozypdfs.conversion.types import BBox

_RENDER_DPI = 150


def crop_to_png(
    doc: pymupdf.Document, page_number: int, bbox: BBox, padding: float = 2.0
) -> tuple[bytes, tuple[int, int]]:
    page = doc[page_number - 1]
    clip = pymupdf.Rect(
        bbox.x0 - padding, bbox.y0 - padding, bbox.x1 + padding, bbox.y1 + padding
    ) & page.rect
    pixmap = page.get_pixmap(clip=clip, dpi=_RENDER_DPI)
    return pixmap.tobytes("png"), (pixmap.width, pixmap.height)
