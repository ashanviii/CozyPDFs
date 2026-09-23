"""Image extraction and caption association.

Every embedded image becomes a visual asset — no OCR, no attempt to
describe or reconstruct its content as text, ever. The only judgment calls
here are which short piece of adjacent text (if any) is actually this
image's caption, and — via layout.py's decorative-image detection, which
this module's `is_decorative_xref` set feeds — whether a repeated logo/
watermark image should be extracted at all.
"""

import re
from dataclasses import replace

import pymupdf

from cozypdfs.conversion.render import crop_to_png
from cozypdfs.conversion.types import PreBlock, RawImage
from cozypdfs.dir.schema import BlockType

_CAPTION_PATTERN = re.compile(
    r"^(figure|fig\.?|table|map|chart|diagram|image)\s*\d*[:.\-]?\s", re.IGNORECASE
)
_CAPTION_WEAK_MAX_WORDS = 15
# Only FIGURE/TABLE get a caption-like association — an equation's
# surrounding prose is normal body text, not a caption, per the product
# rule that prose stays readable directly before and after a preserved
# equation.
_VISUAL_TYPES = {BlockType.FIGURE.value, BlockType.TABLE.value}


def build_image_block(doc: pymupdf.Document, image: RawImage, order_hint: int) -> PreBlock:
    png_bytes, size = crop_to_png(doc, image.page_number, image.bbox, padding=0.0)
    return PreBlock(
        type=BlockType.FIGURE.value,
        content="",
        page_number=image.page_number,
        order_hint=order_hint,
        confidence=1.0,
        preserve_as_image=True,
        asset_bytes=png_bytes,
        asset_size=size,
    )


def associate_captions(blocks: list[PreBlock]) -> list[PreBlock]:
    """A PARAGRAPH block immediately following a visual block is retyped to
    CAPTION when it looks like one — either an explicit "Figure 1: ..."
    style opener, or a short blurb on the same page right after the
    visual. Ordering is untouched; this only changes the block's type."""
    ordered = sorted(blocks, key=lambda b: b.order_hint)
    result = list(ordered)

    for i in range(1, len(result)):
        prev, curr = result[i - 1], result[i]
        if prev.type not in _VISUAL_TYPES or curr.type != BlockType.PARAGRAPH.value:
            continue

        text = curr.content.strip()
        pattern_match = bool(_CAPTION_PATTERN.match(text))
        weak_match = curr.page_number == prev.page_number and len(text.split()) <= _CAPTION_WEAK_MAX_WORDS

        if pattern_match or weak_match:
            result[i] = replace(curr, type=BlockType.CAPTION.value)

    return result
