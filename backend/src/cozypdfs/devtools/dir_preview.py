"""Developer-only visual inspection tool: renders a DIRDocument as a
single, self-contained HTML file — one continuous reading column, no PDF
pages, no PDF columns. It exists to answer exactly one question: "reading
this top to bottom, does the reconstruction actually feel natural?" It is
not the product reader and never will be — no pagination, no themes, no
font controls, nothing but the reconstructed reading order made visible.

Source-page provenance is shown, but confined to a narrow, muted left
gutter next to each block — visible enough to debug ordering, never
inserted into the text flow itself (no "page N" paragraphs interrupting
reading).

Usage: `uv run python -m cozypdfs.devtools.dir_preview <pdf-path> [out.html]`
reconstructs the given PDF and writes a preview next to it (or to the given
path). `render_dir_preview` is the pure, testable rendering function this
CLI wraps.
"""

import base64
import sys
from html import escape
from pathlib import Path

from cozypdfs.dir.schema import Asset, Block, BlockType, DIRDocument
from cozypdfs.storage.base import StorageBackend

_LOW_CONFIDENCE_THRESHOLD = 0.6


def render_dir_preview(document: DIRDocument, storage: StorageBackend, *, title: str = "DIR preview") -> str:
    assets_by_id = {asset.id: asset for asset in document.assets}

    sections: list[str] = []
    for chapter in document.chapters:
        if chapter.title:
            sections.append(f'<h1 class="chapter-title">{escape(chapter.title)}</h1>')
        for block in chapter.blocks:
            sections.append(_render_block(block, assets_by_id, storage))

    meta_bits = [escape(document.meta.title or "(untitled)")]
    if document.meta.author:
        meta_bits.append(f"by {escape(document.meta.author)}")

    return _PAGE_TEMPLATE.format(
        title=escape(title),
        meta=" &middot; ".join(meta_bits),
        block_count=sum(len(c.blocks) for c in document.chapters),
        body="\n".join(sections),
    )


def _render_block(block: Block, assets_by_id: dict[str, Asset], storage: StorageBackend) -> str:
    inner = _render_block_content(block, assets_by_id, storage)
    low_confidence = block.preserve_as_image and block.confidence < _LOW_CONFIDENCE_THRESHOLD
    classes = f"block block--{block.type.value}" + (" block--low-confidence" if low_confidence else "")
    provenance = f"p.{block.source_page}" if block.source_page is not None else ""
    confidence_label = f"conf {block.confidence:.1f}" if block.preserve_as_image else ""

    return (
        f'<div class="{classes}" data-page="{block.source_page or ""}">'
        f'<div class="gutter"><span class="prov">{provenance}</span>'
        f'<span class="conf">{confidence_label}</span></div>'
        f'<div class="content">{inner}</div>'
        f"</div>"
    )


def _render_block_content(block: Block, assets_by_id: dict[str, Asset], storage: StorageBackend) -> str:
    if block.preserve_as_image:
        return _render_asset(block, assets_by_id, storage)
    # PARAGRAPH/HEADING/LIST/TABLE/FOOTNOTE/CAPTION already carry their own
    # semantic HTML fragment (see conversion/assembly.py) — render as-is.
    return block.content


def _render_asset(block: Block, assets_by_id: dict[str, Asset], storage: StorageBackend) -> str:
    asset = assets_by_id.get(block.asset_id) if block.asset_id else None
    if asset is None:
        return '<p class="asset-missing">(missing asset)</p>'

    try:
        data = storage.get(asset.storage_key)
    except Exception:  # noqa: BLE001 - the preview must degrade, not crash, on a missing file
        return f'<p class="asset-missing">(could not load asset {escape(asset.id)})</p>'

    encoded = base64.b64encode(data).decode("ascii")
    alt = escape(asset.alt_text or block.type.value)
    label = {
        BlockType.EQUATION: "Equation (preserved as image)",
        BlockType.TABLE: "Table (preserved as image — low reconstruction confidence)",
        BlockType.FIGURE: "Figure",
        BlockType.IMAGE: "Image",
    }.get(block.type, "Preserved image")
    width_attr = f' width="{asset.width}"' if asset.width else ""
    height_attr = f' height="{asset.height}"' if asset.height else ""

    return (
        f'<figure class="asset">'
        f'<img src="data:image/png;base64,{encoded}" alt="{alt}"{width_attr}{height_attr}>'
        f'<figcaption class="asset-label">{escape(label)}</figcaption>'
        f"</figure>"
    )


_PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  :root {{
    --text: #1f2320;
    --muted: #8a8478;
    --bg: #faf9f6;
    --surface: #ffffff;
    --border: #e6e2da;
    --accent: #6b5b4d;
    --low-confidence: #b3543f;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: Georgia, "Times New Roman", serif;
    line-height: 1.65;
  }}
  header {{
    max-width: 760px;
    margin: 0 auto;
    padding: 2rem 1.5rem 0.5rem;
    font-family: -apple-system, sans-serif;
  }}
  header h1 {{ font-size: 1.1rem; margin: 0; color: var(--muted); }}
  header p {{ margin: 0.25rem 0 0; font-size: 0.85rem; color: var(--muted); }}
  main {{
    max-width: 760px;
    margin: 0 auto;
    padding: 1rem 1.5rem 4rem;
  }}
  .block {{
    display: grid;
    grid-template-columns: 44px 1fr;
    gap: 0.75rem;
    align-items: start;
  }}
  .gutter {{
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    font-family: -apple-system, sans-serif;
    font-size: 0.65rem;
    color: var(--muted);
    opacity: 0.55;
    padding-top: 0.3rem;
    user-select: none;
  }}
  .block:hover .gutter {{ opacity: 1; }}
  .content p {{ margin: 0 0 1.1em; font-size: 1.05rem; }}
  .content h1, .content h2, .content h3 {{
    font-family: -apple-system, sans-serif;
    margin: 1.6em 0 0.6em;
    line-height: 1.3;
  }}
  .content ul, .content ol {{ margin: 0 0 1.1em; padding-left: 1.4em; }}
  .content table {{
    border-collapse: collapse;
    margin: 0 0 1.1em;
    font-family: -apple-system, sans-serif;
    font-size: 0.9rem;
  }}
  .content table th, .content table td {{
    border: 1px solid var(--border);
    padding: 0.4em 0.7em;
    text-align: left;
  }}
  .content table th {{ background: var(--surface); }}
  .block--footnote .content p {{
    font-size: 0.85rem;
    color: var(--muted);
    border-left: 2px solid var(--border);
    padding-left: 0.75em;
  }}
  .block--footnote .content p::before {{ content: "note "; font-style: italic; }}
  .block--caption .content figcaption {{
    font-family: -apple-system, sans-serif;
    font-size: 0.85rem;
    font-style: italic;
    color: var(--muted);
    margin: -0.6em 0 1.1em;
  }}
  .asset {{ margin: 0 0 1.1em; }}
  .asset img {{ max-width: 100%; height: auto; border: 1px solid var(--border); border-radius: 4px; }}
  .asset-label {{
    font-family: -apple-system, sans-serif;
    font-size: 0.75rem;
    color: var(--muted);
    margin-top: 0.35em;
  }}
  .asset-missing {{ color: var(--low-confidence); font-family: -apple-system, sans-serif; }}
  .block--low-confidence .content {{ box-shadow: -3px 0 0 var(--low-confidence); padding-left: 0.6em; }}
  .block--low-confidence .gutter .conf {{ color: var(--low-confidence); }}
  .chapter-title {{
    font-family: -apple-system, sans-serif;
    font-size: 1.5rem;
    margin: 2.2em 0 1em;
    padding-top: 1.2em;
    border-top: 1px solid var(--border);
  }}
  .chapter-title:first-child {{ border-top: none; padding-top: 0; margin-top: 0.5em; }}
</style>
</head>
<body>
<header>
  <h1>DIR preview — developer inspection only</h1>
  <p>{meta} &middot; {block_count} blocks &middot; single continuous reading column, not the product reader</p>
</header>
<main>
{body}
</main>
</body>
</html>
"""


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python -m cozypdfs.devtools.dir_preview <pdf-path> [out.html]")
        raise SystemExit(1)

    from cozypdfs.conversion.pipeline import reconstruct_pdf
    from cozypdfs.storage.local import LocalDiskStorage

    pdf_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else pdf_path.with_suffix(".preview.html")
    storage_root = out_path.parent / f"{pdf_path.stem}_assets"

    storage = LocalDiskStorage(storage_root)
    document = reconstruct_pdf(
        pdf_path.read_bytes(), storage=storage, book_id=pdf_path.stem, title=None, author=None
    )
    html = render_dir_preview(document, storage, title=pdf_path.stem)
    out_path.write_text(html, encoding="utf-8")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
