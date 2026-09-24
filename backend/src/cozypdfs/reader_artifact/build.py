"""DIR -> ReaderArtifact. Pure repackaging: no PDF access, no re-running
extraction/layout/paragraph-reconstruction/reading-order logic — every
semantic decision here was already made by Phase 2A. This stage only:

  - derives a nested section/navigation hierarchy from DIR's existing
    heading levels (chapters are level-1 sections; a level>=2 HEADING
    block opens a nested child section instead of remaining a block),
  - merges each DIR CAPTION block into the `caption` field of the FIGURE/
    TABLE block it immediately follows — the same adjacency Phase 2A's
    `figures.associate_captions` already established, just materialized
    as one unit instead of two blocks that merely render next to each
    other,
  - assigns deterministic asset filenames from DIR's existing asset ids.

Never invents a heading, section, or caption relationship DIR doesn't
already support.
"""

import re
from html import unescape

from cozypdfs.dir.schema import Block as DIRBlock
from cozypdfs.dir.schema import BlockType as DIRBlockType
from cozypdfs.dir.schema import Chapter as DIRChapter
from cozypdfs.dir.schema import DIRDocument
from cozypdfs.reader_artifact.schema import (
    NavigationItem,
    ReaderArtifact,
    ReaderAsset,
    ReaderBlock,
    ReaderBlockType,
    ReaderMeta,
    ReaderSection,
)

_ASSET_MEDIA_TYPE = "image/png"  # every Phase 2A asset is a PNG crop (conversion/render.py)

# Only these DIR block types can own a following caption — mirrors
# conversion/figures.py's `_VISUAL_TYPES` exactly (EQUATION is deliberately
# excluded there: prose after an equation stays prose, never a caption).
_CAPTION_OWNER_TYPES = (DIRBlockType.FIGURE, DIRBlockType.TABLE)

_LEADING_TAG_RE = re.compile(r"^<[^>]+>")
_TRAILING_TAG_RE = re.compile(r"</[^>]+>$")


def derive_reader_artifact(document: DIRDocument, *, book_id: str) -> ReaderArtifact:
    assets = [
        ReaderAsset(
            id=asset.id,
            filename=f"{asset.id}.png",
            media_type=_ASSET_MEDIA_TYPE,
            width=asset.width,
            height=asset.height,
            alt_text=asset.alt_text,
        )
        for asset in document.assets
    ]

    sections = [_build_chapter_section(chapter) for chapter in document.chapters]
    navigation = [_section_to_nav(section) for section in sections]

    return ReaderArtifact(
        book_id=book_id,
        dir_schema_version=document.schema_version,
        meta=ReaderMeta(
            title=document.meta.title,
            author=document.meta.author,
            language=document.meta.language,
            source_type=document.meta.source_type,
        ),
        sections=sections,
        assets=assets,
        navigation=navigation,
    )


def _build_chapter_section(chapter: DIRChapter) -> ReaderSection:
    root = ReaderSection(id=chapter.id, title=chapter.title, level=1)
    _fold_blocks_into_sections(chapter.blocks, root)
    return root


def _fold_blocks_into_sections(blocks: list[DIRBlock], root: ReaderSection) -> None:
    stack: list[ReaderSection] = [root]
    caption_owner: ReaderBlock | None = None

    for dir_block in blocks:
        if dir_block.type == DIRBlockType.CAPTION:
            if caption_owner is not None:
                caption_owner.caption = _unwrap_text(dir_block.content)
            else:
                # Defensive only: Phase 2A's associate_captions only ever
                # retypes a paragraph *immediately after* a figure/table,
                # so an orphaned caption should never occur. If it did,
                # inventing an association DIR didn't establish would be
                # worse than keeping it as plain, still-readable content.
                stack[-1].blocks.append(_orphan_caption_block(dir_block))
            caption_owner = None
            continue

        if dir_block.type == DIRBlockType.HEADING and (dir_block.level or 1) >= 2:
            level = dir_block.level or 2
            while len(stack) > 1 and stack[-1].level >= level:
                stack.pop()
            section = ReaderSection(id=f"sec-{dir_block.id}", title=_unwrap_text(dir_block.content), level=level)
            stack[-1].children.append(section)
            stack.append(section)
            caption_owner = None
            continue

        block = _to_reader_block(dir_block)
        stack[-1].blocks.append(block)
        caption_owner = block if dir_block.type in _CAPTION_OWNER_TYPES else None


def _to_reader_block(dir_block: DIRBlock) -> ReaderBlock:
    return ReaderBlock(
        id=dir_block.id,
        type=ReaderBlockType(dir_block.type.value),
        order=dir_block.order,
        content=dir_block.content,
        level=dir_block.level,
        preserve_as_image=dir_block.preserve_as_image,
        asset_id=dir_block.asset_id,
        confidence=dir_block.confidence,
        source_page=dir_block.source_page,
    )


def _orphan_caption_block(dir_block: DIRBlock) -> ReaderBlock:
    text = _unwrap_text(dir_block.content)
    return ReaderBlock(
        id=dir_block.id,
        type=ReaderBlockType.PARAGRAPH,
        order=dir_block.order,
        content=f"<p>{_escape(text)}</p>",
        confidence=dir_block.confidence,
        source_page=dir_block.source_page,
    )


def _unwrap_text(html_fragment: str) -> str:
    """DIR wraps every text-bearing block in exactly one outer tag
    (`<p>...</p>`, `<h2>...</h2>`, `<figcaption>...</figcaption>`) with the
    inner text HTML-escaped (see conversion/assembly.py). This strips that
    single wrapper and unescapes back to plain text for section titles and
    captions, which store plain text — XHTML generation re-escapes it."""
    inner = _LEADING_TAG_RE.sub("", html_fragment)
    inner = _TRAILING_TAG_RE.sub("", inner)
    return unescape(inner)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _section_to_nav(section: ReaderSection) -> NavigationItem:
    return NavigationItem(
        section_id=section.id,
        title=section.title or "Untitled",
        level=section.level,
        children=[_section_to_nav(child) for child in section.children],
    )
