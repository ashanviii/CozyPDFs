"""DIR assembly: turns the ordered PreBlocks into the canonical
DIRDocument — assigning stable block IDs, wrapping plain text into the
semantic HTML fragments Block.content expects, splitting into chapters at
H1-heading boundaries, and turning every preserve_as_image PreBlock into
an Asset entry. Pure and deterministic: the same PreBlocks and book_id
always produce the same DIR.

Chapter splitting is a heuristic, not a guarantee: a document with no H1
headings becomes one implicit chapter rather than failing or guessing.
"""

from cozypdfs.conversion.types import PreBlock
from cozypdfs.dir.schema import Asset, Block, BlockType, Chapter, DIRDocument, DIRMeta


def assemble(
    blocks: list[PreBlock], *, book_id: str, title: str | None, author: str | None
) -> tuple[DIRDocument, list[tuple[str, bytes]]]:
    ordered = sorted(blocks, key=lambda pre: pre.order_hint)

    assets: list[Asset] = []
    assets_to_store: list[tuple[str, bytes]] = []
    dir_blocks: list[Block] = []

    for index, pre in enumerate(ordered):
        asset_id: str | None = None
        if pre.preserve_as_image and pre.asset_bytes is not None:
            asset_id = f"asset-{index}"
            storage_key = f"books/{book_id}/assets/{asset_id}.png"
            width, height = pre.asset_size or (None, None)
            assets.append(
                Asset(id=asset_id, storage_key=storage_key, width=width, height=height, alt_text=pre.asset_alt)
            )
            assets_to_store.append((storage_key, pre.asset_bytes))

        dir_blocks.append(
            Block(
                id=f"b{index}",
                type=BlockType(pre.type),
                order=index,
                content=_render_content(pre),
                confidence=pre.confidence,
                preserve_as_image=pre.preserve_as_image,
                asset_id=asset_id,
                level=pre.level,
                source_page=pre.page_number,
            )
        )

    chapters = _split_into_chapters(ordered, dir_blocks)

    document = DIRDocument(
        meta=DIRMeta(title=title, author=author, language=None, source_type="pdf"),
        chapters=chapters,
        assets=assets,
    )
    return document, assets_to_store


def _render_content(pre: PreBlock) -> str:
    if pre.type == BlockType.PARAGRAPH.value or pre.type == BlockType.FOOTNOTE.value:
        return f"<p>{_escape(pre.content)}</p>"
    if pre.type == BlockType.CAPTION.value:
        return f"<figcaption>{_escape(pre.content)}</figcaption>"
    if pre.type == BlockType.HEADING.value:
        level = pre.level or 1
        return f"<h{level}>{_escape(pre.content)}</h{level}>"
    # LIST/TABLE already carry a built HTML fragment; IMAGE/FIGURE/EQUATION
    # preserved as images carry no text content at all.
    return pre.content


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _split_into_chapters(ordered: list[PreBlock], dir_blocks: list[Block]) -> list[Chapter]:
    chapters: list[Chapter] = []
    current_blocks: list[Block] = []
    current_title: str | None = None

    def flush() -> None:
        if current_blocks or current_title is not None:
            chapters.append(
                Chapter(id=f"ch{len(chapters)}", title=current_title, order=len(chapters), blocks=current_blocks)
            )

    for pre, block in zip(ordered, dir_blocks, strict=True):
        if pre.type == BlockType.HEADING.value and pre.level == 1:
            flush()
            current_blocks = []
            current_title = pre.content
        else:
            current_blocks.append(block)
    flush()

    if not chapters:
        chapters = [Chapter(id="ch0", title=None, order=0, blocks=[])]

    return chapters
