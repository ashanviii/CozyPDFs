"""The full Phase 2B pipeline: DIR -> ReaderArtifact -> EPUB, validated at
both layers, run across the entire golden corpus. This is the formalized
version of the ad-hoc scratch script used during development to sweep all
14 fixtures and inspect them visually — same corpus, now asserted in CI
instead of eyeballed once."""

from pathlib import Path

import pytest

from cozypdfs.conversion.pipeline import reconstruct_pdf
from cozypdfs.epub.pipeline import ReaderArtifactPipelineError, build_reader_artifact_and_epub
from cozypdfs.epub.validation import validate as validate_epub
from cozypdfs.reader_artifact.validation import validate as validate_artifact
from cozypdfs.storage.local import LocalDiskStorage

GOLDEN_DIR = Path(__file__).parent / "golden_pdfs"

ALL_GOLDEN_NAMES = [
    "single_column_prose",
    "two_column",
    "headers_and_page_numbers",
    "footnotes",
    "tables",
    "equations",
    "figures_with_captions",
    "complex_visual",
    "mixed_layout",
    "difficult",
    "three_column",
    "uneven_three_column",
    "mixed_column_counts",
    "realistic_book_excerpt",
]


@pytest.mark.parametrize("name", ALL_GOLDEN_NAMES)
def test_full_pipeline_produces_a_validating_artifact_and_epub(name: str, storage: LocalDiskStorage):
    data = (GOLDEN_DIR / f"{name}.pdf").read_bytes()
    document = reconstruct_pdf(data, storage=storage, book_id=name, title=None, author=None)

    artifact, epub_bytes = build_reader_artifact_and_epub(document, book_id=name, storage=storage)

    assert validate_artifact(artifact) == []
    assert validate_epub(epub_bytes) == []
    assert len(epub_bytes) > 0
    # Sanity bound, not a strict perf assertion: a 14-fixture synthetic
    # corpus should never produce a multi-megabyte EPUB.
    assert len(epub_bytes) < 5_000_000


def test_pipeline_raises_its_own_error_type_when_the_reader_artifact_is_invalid(storage: LocalDiskStorage):
    from cozypdfs.dir.schema import DIRDocument, DIRMeta

    empty_document = DIRDocument(meta=DIRMeta(title="Empty"), chapters=[], assets=[])
    with pytest.raises(ReaderArtifactPipelineError, match="reader artifact validation failed"):
        build_reader_artifact_and_epub(empty_document, book_id="empty", storage=storage)


def test_pipeline_raises_its_own_error_type_when_epub_validation_fails(storage: LocalDiskStorage, monkeypatch):
    import cozypdfs.epub.pipeline as pipeline_module

    monkeypatch.setattr(pipeline_module, "build_epub", lambda *args, **kwargs: b"not a real epub")

    data = (GOLDEN_DIR / "single_column_prose.pdf").read_bytes()
    document = reconstruct_pdf(data, storage=storage, book_id="scp", title=None, author=None)

    with pytest.raises(ReaderArtifactPipelineError, match="EPUB validation failed"):
        build_reader_artifact_and_epub(document, book_id="scp", storage=storage)
