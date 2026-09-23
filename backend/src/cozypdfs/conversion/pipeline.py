"""Top-level orchestration: PDF bytes -> a validated DIRDocument, with all
extracted image assets stored via StorageBackend. This is the only place
in the conversion package that touches storage — every stage above it
returns pure data; `reconstruct_pdf` is the seam the job handler (Phase 2A
integration) and any offline/debug tooling both call through.

Deterministic: given the same bytes and book_id, produces the same DIR
every time — no network calls, no randomness anywhere in the pipeline.
"""

import pymupdf

from cozypdfs.conversion import (
    assembly,
    classify,
    layout,
    reading_order,
    semantic,
    tables,
    validation,
)
from cozypdfs.conversion.analysis import analyze_document
from cozypdfs.dir.schema import DIRDocument
from cozypdfs.storage.base import StorageBackend


class ReconstructionError(Exception):
    pass


def reconstruct_pdf(
    data: bytes,
    *,
    storage: StorageBackend,
    book_id: str,
    title: str | None,
    author: str | None,
) -> DIRDocument:
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        pages = analyze_document(doc)
        table_regions = tables.detect_tables(doc)
        layout_result = layout.analyze_layout(pages, table_regions)
        ordered_items = reading_order.build_reading_order(layout_result, table_regions)
        classified_items = classify.classify_items(ordered_items, layout_result.dominant_body_size)
        blocks = semantic.build_blocks(doc, classified_items)
        document, assets_to_store = assembly.assemble(blocks, book_id=book_id, title=title, author=author)
    finally:
        doc.close()

    issues = validation.validate(document)
    if issues:
        raise ReconstructionError("; ".join(issue.message for issue in issues))

    for storage_key, png_bytes in assets_to_store:
        storage.put(storage_key, png_bytes, content_type="image/png")

    return document
