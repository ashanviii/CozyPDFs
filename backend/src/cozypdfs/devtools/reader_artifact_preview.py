"""Developer-only visual inspection tool for the Phase 2B reader artifact
— the Phase 2A `dir_preview.py` pattern, adapted to the artifact's nested
section structure instead of DIR's flat chapter/block list. Same intent:
one continuous reading column, no PDF pages, no PDF columns, provenance
confined to a muted left gutter, low-confidence preserved content flagged.

The one structural difference worth inspecting visually: a figure/table's
caption is already merged into the block (`block.caption`), not a
separate adjacent block — this preview renders that merge directly, which
is itself a way to sanity-check reader_artifact/build.py's figure/caption
handling by eye.
"""

import base64
import sys
from html import escape
from pathlib import Path

from cozypdfs.reader_artifact.schema import ReaderArtifact, ReaderAsset, ReaderBlock, ReaderSection
from cozypdfs.storage.base import StorageBackend

_LOW_CONFIDENCE_THRESHOLD = 0.6


def render_reader_artifact_preview(
    artifact: ReaderArtifact,
    storage: StorageBackend,
    *,
    asset_storage_keys: dict[str, str],
    title: str = "Reader artifact preview",
) -> str:
    """`asset_storage_keys` maps ReaderAsset.id -> where its bytes actually
    live in storage. A ReaderAsset deliberately carries no storage path of
    its own (see schema.py) — only a caller that also has the source DIR
    (which does track storage keys) can resolve one, so it's supplied
    explicitly here rather than guessed from the asset id."""
    assets_by_id = {asset.id: asset for asset in artifact.assets}
    sections_html = "\n".join(
        _render_section(section, assets_by_id, asset_storage_keys, storage) for section in artifact.sections
    )

    meta_bits = [escape(artifact.meta.title or "(untitled)")]
    if artifact.meta.author:
        meta_bits.append(f"by {escape(artifact.meta.author)}")

    return _PAGE_TEMPLATE.format(
        title=escape(title),
        meta=" &middot; ".join(meta_bits),
        section_count=_count_sections(artifact.sections),
        body=sections_html,
    )


def _count_sections(sections: list[ReaderSection]) -> int:
    return len(sections) + sum(_count_sections(s.children) for s in sections)


def _render_section(
    section: ReaderSection,
    assets_by_id: dict[str, ReaderAsset],
    asset_storage_keys: dict[str, str],
    storage: StorageBackend,
) -> str:
    parts = []
    if section.title:
        level = min(max(section.level, 1), 3)
        css_class = "chapter-title" if section.level == 1 else "section-title"
        parts.append(f'<h{level} class="{css_class}">{escape(section.title)}</h{level}>')
    for block in section.blocks:
        parts.append(_render_block(block, assets_by_id, asset_storage_keys, storage))
    for child in section.children:
        nested = _render_section(child, assets_by_id, asset_storage_keys, storage)
        parts.append(f'<div class="nested-section">{nested}</div>')
    return "\n".join(parts)


def _render_block(
    block: ReaderBlock,
    assets_by_id: dict[str, ReaderAsset],
    asset_storage_keys: dict[str, str],
    storage: StorageBackend,
) -> str:
    inner = (
        _render_asset(block, assets_by_id, asset_storage_keys, storage)
        if block.preserve_as_image
        else block.content
    )
    if block.caption and not block.preserve_as_image:
        # defensive: should never happen (only preserved visual blocks
        # carry a caption today), but never hide it if it does
        inner += f"<figcaption>{escape(block.caption)}</figcaption>"

    low_confidence = block.preserve_as_image and block.confidence < _LOW_CONFIDENCE_THRESHOLD
    classes = f"block block--{block.type.value}" + (" block--low-confidence" if low_confidence else "")
    provenance = f"p.{block.source_page}" if block.source_page is not None else ""
    confidence_label = f"conf {block.confidence:.1f}" if block.preserve_as_image else ""

    return (
        f'<div class="{classes}">'
        f'<div class="gutter"><span class="prov">{provenance}</span>'
        f'<span class="conf">{confidence_label}</span></div>'
        f'<div class="content">{inner}</div>'
        f"</div>"
    )


def _render_asset(
    block: ReaderBlock,
    assets_by_id: dict[str, ReaderAsset],
    asset_storage_keys: dict[str, str],
    storage: StorageBackend,
) -> str:
    asset = assets_by_id.get(block.asset_id) if block.asset_id else None
    storage_key = asset_storage_keys.get(block.asset_id or "")
    if asset is None or storage_key is None:
        return '<p class="asset-missing">(missing asset)</p>'
    try:
        data = storage.get(storage_key)
    except Exception:  # noqa: BLE001 - the preview must degrade, not crash, on a missing file
        return f'<p class="asset-missing">(could not load asset {escape(asset.id)})</p>'
    encoded = base64.b64encode(data).decode("ascii")
    alt = escape(block.caption or asset.alt_text or block.type.value)
    caption = f"<figcaption>{escape(block.caption)}</figcaption>" if block.caption else ""
    return f'<figure><img src="data:{asset.media_type};base64,{encoded}" alt="{alt}"/>{caption}</figure>'


_PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  :root {{ --text:#1f2320; --muted:#8a8478; --bg:#faf9f6; --surface:#fff; --border:#e6e2da; --low:#b3543f; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--text); font-family:Georgia,"Times New Roman",serif; line-height:1.65; }}
  header {{ max-width:760px; margin:0 auto; padding:2rem 1.5rem 0.5rem; font-family:-apple-system,sans-serif; }}
  header h1 {{ font-size:1.1rem; margin:0; color:var(--muted); }}
  header p {{ margin:0.25rem 0 0; font-size:0.85rem; color:var(--muted); }}
  main {{ max-width:760px; margin:0 auto; padding:1rem 1.5rem 4rem; }}
  .nested-section {{ margin-left: 1.25rem; border-left: 2px solid var(--border); padding-left: 1rem; }}
  .block {{ display:grid; grid-template-columns:44px 1fr; gap:0.75rem; align-items:start; }}
  .gutter {{ display:flex; flex-direction:column; align-items:flex-end; font-family:-apple-system,sans-serif; font-size:0.65rem; color:var(--muted); opacity:0.55; padding-top:0.3rem; }}
  .block:hover .gutter {{ opacity:1; }}
  .content p {{ margin:0 0 1.1em; font-size:1.05rem; }}
  .content ul, .content ol {{ margin:0 0 1.1em; padding-left:1.4em; }}
  .content table {{ border-collapse:collapse; margin:0 0 1.1em; font-family:-apple-system,sans-serif; font-size:0.9rem; }}
  .content table th, .content table td {{ border:1px solid var(--border); padding:0.4em 0.7em; text-align:left; }}
  .content table th {{ background:var(--surface); }}
  .block--footnote .content p {{ font-size:0.85rem; color:var(--muted); border-left:2px solid var(--border); padding-left:0.75em; }}
  .asset {{ margin:0 0 1.1em; }}
  .asset img, figure img {{ max-width:100%; border:1px solid var(--border); border-radius:4px; }}
  figcaption {{ font-family:-apple-system,sans-serif; font-size:0.85rem; font-style:italic; color:var(--muted); margin-top:0.35em; }}
  .asset-missing {{ color:var(--low); font-family:-apple-system,sans-serif; }}
  .block--low-confidence .content {{ box-shadow:-3px 0 0 var(--low); padding-left:0.6em; }}
  .block--low-confidence .gutter .conf {{ color:var(--low); }}
  .chapter-title {{ font-family:-apple-system,sans-serif; font-size:1.5rem; margin:2.2em 0 1em; padding-top:1.2em; border-top:1px solid var(--border); }}
  .chapter-title:first-child {{ border-top:none; padding-top:0; margin-top:0.5em; }}
  .section-title {{ font-family:-apple-system,sans-serif; font-size:1.15rem; margin:1.4em 0 0.8em; }}
</style>
</head>
<body>
<header>
  <h1>Reader artifact preview — developer inspection only</h1>
  <p>{meta} &middot; {section_count} sections &middot; single continuous reading column, not the product reader</p>
</header>
<main>
{body}
</main>
</body>
</html>
"""


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python -m cozypdfs.devtools.reader_artifact_preview <pdf-path> [out.html]")
        raise SystemExit(1)

    from cozypdfs.conversion.pipeline import reconstruct_pdf
    from cozypdfs.reader_artifact.build import derive_reader_artifact
    from cozypdfs.storage.local import LocalDiskStorage

    pdf_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else pdf_path.with_suffix(".artifact.html")
    storage_root = out_path.parent / f"{pdf_path.stem}_ra_assets"

    storage = LocalDiskStorage(storage_root)
    document = reconstruct_pdf(
        pdf_path.read_bytes(), storage=storage, book_id=pdf_path.stem, title=None, author=None
    )
    artifact = derive_reader_artifact(document, book_id=pdf_path.stem)
    asset_storage_keys = {asset.id: asset.storage_key for asset in document.assets}
    html = render_reader_artifact_preview(
        artifact, storage, asset_storage_keys=asset_storage_keys, title=pdf_path.stem
    )
    out_path.write_text(html, encoding="utf-8")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
