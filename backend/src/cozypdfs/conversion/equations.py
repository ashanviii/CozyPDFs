"""Equation preservation. No math reconstruction is attempted in V1 — a
line classify.py flagged as equation-like (dense in math symbols) is
cropped to an image asset and dropped into the flow in its place, so the
surrounding prose stays normal reflowable text on either side and the
equation's position in reading order is preserved exactly.
"""

import pymupdf

from cozypdfs.conversion.render import crop_to_png
from cozypdfs.conversion.types import ClassifiedLine, PreBlock
from cozypdfs.dir.schema import BlockType

_EQUATION_CONFIDENCE = 0.3  # a heuristic symbol-density flag, not a verified read — low on purpose


def build_equation_block(doc: pymupdf.Document, item: ClassifiedLine, order_hint: int) -> PreBlock:
    png_bytes, size = crop_to_png(doc, item.line.page_number, item.line.bbox)
    return PreBlock(
        type=BlockType.EQUATION.value,
        content="",
        page_number=item.line.page_number,
        order_hint=order_hint,
        confidence=_EQUATION_CONFIDENCE,
        preserve_as_image=True,
        asset_bytes=png_bytes,
        asset_size=size,
        asset_alt="Equation preserved as an image",
    )
