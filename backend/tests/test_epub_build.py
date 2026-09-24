"""EPUB generation from a ReaderArtifact: structural correctness via the
custom validator, and — because the whole point of the zip-timestamp and
OPF dcterms:modified fixes was byte-for-byte determinism — direct
byte-equality tests, not just "validates both times"."""

import time
from pathlib import Path

from cozypdfs.conversion.pipeline import reconstruct_pdf
from cozypdfs.epub.build import build_epub
from cozypdfs.epub.validation import validate as validate_epub
from cozypdfs.reader_artifact.build import derive_reader_artifact
from cozypdfs.reader_artifact.schema import (
    ReaderArtifact,
    ReaderAsset,
    ReaderBlock,
    ReaderBlockType,
    ReaderMeta,
    ReaderSection,
)
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

# A minimal valid 1x1 PNG (not exercised by ebooklib's own validity checks,
# but keeps the fixture honest about what an "asset" actually is).
_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _minimal_artifact_with_asset(storage: LocalDiskStorage) -> tuple[ReaderArtifact, dict[str, str]]:
    storage_key = "assets/asset-1.png"
    storage.put(storage_key, _TINY_PNG, content_type="image/png")

    figure = ReaderBlock(
        id="b1",
        type=ReaderBlockType.FIGURE,
        order=0,
        content="",
        preserve_as_image=True,
        asset_id="asset-1",
        caption="A tiny figure",
    )
    para = ReaderBlock(id="b2", type=ReaderBlockType.PARAGRAPH, order=1, content="<p>Hello world.</p>")
    section = ReaderSection(id="s1", title="Chapter One", level=1, blocks=[figure, para])
    artifact = ReaderArtifact(
        book_id="book-1",
        dir_schema_version=2,
        meta=ReaderMeta(title="A Tiny Book", author="Author A", language="en"),
        sections=[section],
        assets=[ReaderAsset(id="asset-1", filename="asset-1.png", media_type="image/png")],
        navigation=[],
    )
    return artifact, {"asset-1": storage_key}


def test_build_epub_produces_a_structurally_valid_epub(storage: LocalDiskStorage):
    artifact, asset_keys = _minimal_artifact_with_asset(storage)
    epub_bytes = build_epub(artifact, storage=storage, asset_storage_keys=asset_keys)
    assert validate_epub(epub_bytes) == []


def test_build_epub_embeds_the_actual_asset_bytes(storage: LocalDiskStorage):
    import io
    import zipfile

    artifact, asset_keys = _minimal_artifact_with_asset(storage)
    epub_bytes = build_epub(artifact, storage=storage, asset_storage_keys=asset_keys)

    zf = zipfile.ZipFile(io.BytesIO(epub_bytes))
    matches = [n for n in zf.namelist() if n.endswith("assets/asset-1.png")]
    assert len(matches) == 1
    assert zf.read(matches[0]) == _TINY_PNG


def test_build_epub_includes_a_stylesheet_item(storage: LocalDiskStorage):
    import io
    import zipfile

    artifact, asset_keys = _minimal_artifact_with_asset(storage)
    epub_bytes = build_epub(artifact, storage=storage, asset_storage_keys=asset_keys)
    zf = zipfile.ZipFile(io.BytesIO(epub_bytes))
    assert any(n.endswith("style/style.css") for n in zf.namelist())


def test_build_epub_is_byte_for_byte_deterministic(storage: LocalDiskStorage):
    artifact, asset_keys = _minimal_artifact_with_asset(storage)

    first = build_epub(artifact, storage=storage, asset_storage_keys=asset_keys)
    time.sleep(1.2)  # real wall-clock gap: proves no timestamp leaks through
    second = build_epub(artifact, storage=storage, asset_storage_keys=asset_keys)

    assert first == second


def test_build_epub_zip_entries_carry_no_wall_clock_timestamp(storage: LocalDiskStorage):
    import io
    import zipfile

    artifact, asset_keys = _minimal_artifact_with_asset(storage)
    epub_bytes = build_epub(artifact, storage=storage, asset_storage_keys=asset_keys)
    zf = zipfile.ZipFile(io.BytesIO(epub_bytes))
    for info in zf.infolist():
        assert info.date_time == (1980, 1, 1, 0, 0, 0)


def test_build_epub_opf_metadata_carries_no_wall_clock_timestamp(storage: LocalDiskStorage):
    import io
    import zipfile

    artifact, asset_keys = _minimal_artifact_with_asset(storage)
    epub_bytes = build_epub(artifact, storage=storage, asset_storage_keys=asset_keys)
    zf = zipfile.ZipFile(io.BytesIO(epub_bytes))
    opf_name = next(n for n in zf.namelist() if n.endswith(".opf"))
    opf_text = zf.read(opf_name).decode("utf-8")
    assert "1980-01-01" in opf_text


def test_build_epub_missing_asset_storage_key_raises(storage: LocalDiskStorage):
    artifact, _ = _minimal_artifact_with_asset(storage)
    try:
        build_epub(artifact, storage=storage, asset_storage_keys={})
    except KeyError:
        pass
    else:
        raise AssertionError("expected a KeyError for a missing asset storage key")


# ---------------------------------------------------------------------
# Golden-corpus: full DIR -> ReaderArtifact -> EPUB pipeline
# ---------------------------------------------------------------------


def _build_epub_for(name: str, storage: LocalDiskStorage):
    data = (GOLDEN_DIR / f"{name}.pdf").read_bytes()
    doc = reconstruct_pdf(data, storage=storage, book_id=name, title=None, author=None)
    artifact = derive_reader_artifact(doc, book_id=name)
    asset_keys = {a.id: a.storage_key for a in doc.assets}
    return build_epub(artifact, storage=storage, asset_storage_keys=asset_keys)


def test_every_golden_pdf_produces_a_structurally_valid_epub(storage: LocalDiskStorage):
    for name in ALL_GOLDEN_NAMES:
        epub_bytes = _build_epub_for(name, storage)
        issues = validate_epub(epub_bytes)
        assert issues == [], f"{name}: {[i.message for i in issues]}"


def test_golden_pdf_epub_generation_is_deterministic(storage: LocalDiskStorage, tmp_path):
    other_storage = LocalDiskStorage(tmp_path / "storage2")
    first = _build_epub_for("mixed_layout", storage)
    second = _build_epub_for("mixed_layout", other_storage)
    assert first == second


def test_table_epub_preserves_the_clean_table_as_real_markup_and_the_complex_one_as_an_image(
    storage: LocalDiskStorage,
):
    import io
    import zipfile

    epub_bytes = _build_epub_for("tables", storage)
    zf = zipfile.ZipFile(io.BytesIO(epub_bytes))
    content_files = [n for n in zf.namelist() if n.endswith(".xhtml") and "nav" not in n]
    assert len(content_files) == 1
    xhtml = zf.read(content_files[0]).decode("utf-8")

    assert "<table>" in xhtml
    assert "John" in xhtml and "India" in xhtml
    assert "<figure" in xhtml and "<img" in xhtml
