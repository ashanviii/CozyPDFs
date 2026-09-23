"""Stage-by-stage debug dumps.

The pipeline has eight stages, and when a paragraph comes out wrong, the
question is always "which stage broke it": did extraction misread the
font, did reading order put lines in the wrong sequence, did paragraph
reconstruction join or split incorrectly, did structure classification
pick the wrong block type, or did the EPUB generator render it wrong?

This module serializes each stage's actual output to JSON so that
question has a direct answer instead of a guess. `ConversionPipeline.convert`
calls these when given a `debug_dir`; each function is also independently
usable (e.g. from a notebook) against any stage's output.

Raw PDF coordinates appear here -- and only here. They are exactly the
"source metadata for debugging" the architecture calls for: useful for
diagnosing extraction, never allowed to reach the `Book` model or the
EPUB.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .epub.validator import ValidationResult
from .models import (
    Block,
    Blockquote,
    Book,
    Chapter,
    Epigraph,
    EquationBlock,
    Footnote,
    Heading,
    ImageBlock,
    LayoutRegion,
    ListBlock,
    Paragraph,
    ParagraphCandidate,
    PageLayout,
    Poem,
    RawDocument,
    Run,
    SceneBreak,
    TableBlock,
)


def dump_raw_document(doc: RawDocument, path: Path) -> None:
    data = {
        "source_path": str(doc.source_path),
        "page_count": doc.page_count,
        "pages": [_raw_page_to_dict(p) for p in doc.pages],
    }
    _write_json(path, data)


def _raw_page_to_dict(page) -> dict[str, Any]:
    return {
        "index": page.index,
        "width": page.width,
        "height": page.height,
        "blocks": [_raw_block_to_dict(b) for b in page.blocks],
    }


def _raw_block_to_dict(block) -> dict[str, Any]:
    out: dict[str, Any] = {"type": block.block_type.value, "bbox": _bbox(block.bbox)}
    if block.image is not None:
        img = block.image
        out["image"] = {
            "bbox": _bbox(img.bbox),
            "width": img.width,
            "height": img.height,
            "mime_type": img.mime_type,
            "byte_count": len(img.data),
        }
    out["lines"] = [
        {
            "bbox": _bbox(line.bbox),
            "text": line.text,
            "spans": [
                {
                    "text": s.text,
                    "bbox": _bbox(s.bbox),
                    "font_name": s.font_name,
                    "font_size": round(s.font_size, 2),
                    "bold": s.bold,
                    "italic": s.italic,
                    "superscript": s.superscript,
                }
                for s in line.spans
            ],
        }
        for line in block.lines
    ]
    return out


def dump_page_layouts(layouts: list[PageLayout], path: Path) -> None:
    data = [
        {
            "page_index": pl.page_index,
            "width": pl.width,
            "height": pl.height,
            "column_count": pl.column_count,
            "regions": [_region_to_dict(r) for r in pl.regions],
        }
        for pl in layouts
    ]
    _write_json(path, data)


def dump_regions(regions: list[LayoutRegion], path: Path) -> None:
    """Used for both the reading-order output and the post-artifact-removal output."""
    _write_json(path, [_region_to_dict(r) for r in regions])


def _region_to_dict(region: LayoutRegion) -> dict[str, Any]:
    text = " ".join(line.text for line in region.block.lines) if region.block.lines else ""
    return {
        "page_index": region.page_index,
        "region_type": region.region_type.value,
        "column_index": region.column_index,
        "bbox": _bbox(region.block.bbox),
        "text": text,
    }


def dump_removed_artifacts(
    before: list[LayoutRegion], after: list[LayoutRegion], path: Path
) -> None:
    """What artifact removal actually dropped, and why -- for auditing false positives/negatives."""
    kept_ids = {id(r) for r in after}
    removed = [r for r in before if id(r) not in kept_ids]
    _write_json(path, [_region_to_dict(r) for r in removed])


def dump_paragraph_candidates(candidates: list[ParagraphCandidate], path: Path) -> None:
    data = [
        {
            "rough_kind": c.rough_kind.value,
            "source_pages": c.source_pages,
            "text": c.text,
            "signals": {
                "centered": c.centered,
                "indented": c.indented,
                "block_indented": c.block_indented,
                "starts_with_quote": c.starts_with_quote,
                "is_all_caps": c.is_all_caps,
                "max_font_size": round(c.max_font_size, 2),
                "avg_font_size": round(c.avg_font_size, 2),
                "bold_fraction": round(c.bold_fraction, 2),
                "short_line_fraction": round(c.short_line_fraction, 2),
                "line_count": len(c.line_groups),
            },
        }
        for c in candidates
    ]
    _write_json(path, data)


def dump_book(book: Book, path: Path) -> None:
    data = {
        "metadata": {
            "title": book.metadata.title,
            "author": book.metadata.author,
            "language": book.metadata.language,
        },
        "cover": _asset_summary(book.cover),
        "chapters": [_chapter_to_dict(c) for c in book.chapters],
    }
    _write_json(path, data)


def _chapter_to_dict(chapter: Chapter) -> dict[str, Any]:
    return {
        "id": chapter.id,
        "kind": chapter.kind.value,
        "number": chapter.number,
        "title": chapter.title,
        "blocks": [_block_to_dict(b) for b in chapter.blocks],
    }


def _block_to_dict(block: Block) -> dict[str, Any]:
    if isinstance(block, Paragraph):
        return {"block": "paragraph", "variant": block.variant.value, "text": _runs_text(block.runs), "runs": [_run_to_dict(r) for r in block.runs]}
    if isinstance(block, Heading):
        return {"block": "heading", "level": block.level, "text": _runs_text(block.runs)}
    if isinstance(block, Blockquote):
        return {"block": "blockquote", "attribution": block.attribution, "text": _runs_text(block.runs)}
    if isinstance(block, Epigraph):
        return {"block": "epigraph", "attribution": block.attribution, "text": _runs_text(block.runs)}
    if isinstance(block, SceneBreak):
        return {"block": "scene_break", "marker": block.marker}
    if isinstance(block, Poem):
        return {
            "block": "poem",
            "attribution": block.attribution,
            "lines": [_runs_text(line) for line in block.lines],
        }
    if isinstance(block, Footnote):
        return {"block": "footnote", "marker": block.marker, "text": _runs_text(block.runs)}
    if isinstance(block, ImageBlock):
        return {
            "block": "image",
            "alt_text": block.alt_text,
            "caption": _runs_text(block.caption),
            "asset": _asset_summary(block.asset),
        }
    if isinstance(block, ListBlock):
        return {
            "block": "list",
            "ordered": block.ordered,
            "items": [_runs_text(item) for item in block.items],
        }
    if isinstance(block, TableBlock):
        return {
            "block": "table",
            "rows": [[_runs_text(cell) for cell in row] for row in block.rows],
        }
    if isinstance(block, EquationBlock):
        return {"block": "equation", "latex": block.latex, "has_mathml": bool(block.mathml), "has_image": block.asset is not None}
    return {"block": type(block).__name__}


def _run_to_dict(run: Run) -> dict[str, Any]:
    return {
        "text": run.text,
        "italic": run.italic,
        "bold": run.bold,
        "superscript": run.superscript,
        "subscript": run.subscript,
        "footnote_ref": run.footnote_ref,
    }


def _runs_text(runs: list[Run]) -> str:
    return "".join(r.text for r in runs)


def _asset_summary(asset) -> dict[str, Any] | None:
    if asset is None:
        return None
    return {
        "id": asset.id,
        "mime_type": asset.mime_type,
        "width": asset.width,
        "height": asset.height,
        "byte_count": len(asset.data),
    }


def dump_validation(result: ValidationResult, path: Path) -> None:
    _write_json(
        path,
        {"is_valid": result.is_valid, "errors": result.errors, "warnings": result.warnings},
    )


def _bbox(bbox) -> list[float]:
    return [round(bbox.x0, 2), round(bbox.y0, 2), round(bbox.x1, 2), round(bbox.y1, 2)]


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
