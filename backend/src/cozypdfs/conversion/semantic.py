"""Semantic reconstruction: the single walk over the classified, ordered
sequence that decides block boundaries — merging consecutive BODY/FOOTNOTE
lines into paragraphs (using paragraphs.py's continuation heuristic) and
consecutive LIST_ITEM lines into one list, while HEADING/EQUATION lines and
images/tables are handed off to their own resolvers. Every other
conversion module only classifies or resolves individual items; this is
the one place that groups them.
"""

import pymupdf

from cozypdfs.conversion import equations, figures, lists, paragraphs, tables
from cozypdfs.conversion.types import (
    ClassifiedLine,
    LineRole,
    OrderedItem,
    PreBlock,
    RawImage,
    TableRegion,
)
from cozypdfs.dir.schema import BlockType


def build_blocks(doc: pymupdf.Document, items: list[OrderedItem]) -> list[PreBlock]:
    # Only BODY/FOOTNOTE lines ever get merged into multi-line blocks, so
    # only their gaps belong in the "normal line spacing" statistic — a
    # heading-to-body or list-to-body transition gap is always a block
    # boundary, never a within-paragraph wrap, and would corrupt the
    # baseline if mixed in.
    mergeable_roles = (LineRole.BODY, LineRole.FOOTNOTE)
    gap = paragraphs.typical_line_gap(
        [item for item in items if isinstance(item, ClassifiedLine) and item.role in mergeable_roles]
    )

    blocks: list[PreBlock] = []
    body_run: list[ClassifiedLine] = []
    footnote_run: list[ClassifiedLine] = []
    list_run: list[ClassifiedLine] = []
    order = 0

    def next_order() -> int:
        nonlocal order
        order += 1
        return order

    def flush_body() -> None:
        nonlocal body_run
        if body_run:
            blocks.append(_text_block(BlockType.PARAGRAPH, body_run, next_order()))
            body_run = []

    def flush_footnote() -> None:
        nonlocal footnote_run
        if footnote_run:
            blocks.append(_text_block(BlockType.FOOTNOTE, footnote_run, next_order()))
            footnote_run = []

    def flush_list() -> None:
        nonlocal list_run
        if list_run:
            blocks.append(
                PreBlock(
                    type=BlockType.LIST.value,
                    content=lists.build_list_html(list_run),
                    page_number=list_run[0].line.page_number,
                    order_hint=next_order(),
                    confidence=1.0,
                )
            )
            list_run = []

    def flush_all() -> None:
        flush_body()
        flush_footnote()
        flush_list()

    for item in items:
        if isinstance(item, ClassifiedLine):
            if item.role == LineRole.BODY:
                if body_run and not paragraphs.is_continuation(body_run[-1], item, gap):
                    flush_body()
                flush_footnote()
                flush_list()
                body_run.append(item)
            elif item.role == LineRole.FOOTNOTE:
                if footnote_run and not paragraphs.is_continuation(footnote_run[-1], item, gap):
                    flush_footnote()
                flush_body()
                flush_list()
                footnote_run.append(item)
            elif item.role == LineRole.LIST_ITEM:
                flush_body()
                flush_footnote()
                list_run.append(item)
            elif item.role == LineRole.HEADING:
                flush_all()
                blocks.append(
                    PreBlock(
                        type=BlockType.HEADING.value,
                        content=item.line.text.strip(),
                        page_number=item.line.page_number,
                        order_hint=next_order(),
                        confidence=1.0,
                        level=item.heading_level,
                    )
                )
            elif item.role == LineRole.EQUATION:
                flush_all()
                blocks.append(equations.build_equation_block(doc, item, next_order()))
        elif isinstance(item, RawImage):
            flush_all()
            blocks.append(figures.build_image_block(doc, item, next_order()))
        elif isinstance(item, TableRegion):
            flush_all()
            blocks.append(tables.build_table_block(doc, item, next_order()))

    flush_all()

    return figures.associate_captions(blocks)


def _text_block(block_type: BlockType, run: list[ClassifiedLine], order_hint: int) -> PreBlock:
    return PreBlock(
        type=block_type.value,
        content=paragraphs.join_text(run),
        page_number=run[0].line.page_number,
        order_hint=order_hint,
        confidence=1.0,
    )
