"""Custom structural EPUB validator: negative tests, one invariant at a
time, proving the validator actually catches broken input rather than
rubber-stamping it. See epub/validation.py's module docstring for exactly
what is and isn't checked (no EPUBCheck/JVM available in this
environment)."""

import io
import zipfile
from xml.etree import ElementTree as ET

from cozypdfs.epub.build import build_epub
from cozypdfs.epub.validation import validate as validate_epub
from cozypdfs.reader_artifact.schema import (
    ReaderArtifact,
    ReaderAsset,
    ReaderBlock,
    ReaderBlockType,
    ReaderMeta,
    ReaderSection,
)
from cozypdfs.storage.local import LocalDiskStorage

_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _valid_epub_bytes(storage: LocalDiskStorage) -> bytes:
    storage_key = "assets/asset-1.png"
    storage.put(storage_key, _TINY_PNG, content_type="image/png")
    figure = ReaderBlock(
        id="b1", type=ReaderBlockType.FIGURE, order=0, content="", preserve_as_image=True, asset_id="asset-1"
    )
    section = ReaderSection(id="s1", title="Chapter One", level=1, blocks=[figure])
    artifact = ReaderArtifact(
        book_id="book-1",
        dir_schema_version=2,
        meta=ReaderMeta(title="T", language="en"),
        sections=[section],
        assets=[ReaderAsset(id="asset-1", filename="asset-1.png", media_type="image/png")],
        navigation=[],
    )
    return build_epub(artifact, storage=storage, asset_storage_keys={"asset-1": storage_key})


def _rewrite_zip(epub_bytes: bytes, transform) -> bytes:
    """Extracts every entry, lets `transform(name, data) -> data|None` edit
    or drop it, and re-packs — used to construct deliberately-broken EPUBs
    from a known-good starting point rather than hand-writing a zip."""
    src = zipfile.ZipFile(io.BytesIO(epub_bytes))
    out_buffer = io.BytesIO()
    with zipfile.ZipFile(out_buffer, "w") as out:
        for info in src.infolist():
            data = transform(info.filename, src.read(info.filename))
            if data is not None:
                out.writestr(info, data)
    return out_buffer.getvalue()


def test_a_genuinely_valid_epub_has_no_issues(storage: LocalDiskStorage):
    assert validate_epub(_valid_epub_bytes(storage)) == []


def test_not_a_zip_file_is_flagged():
    issues = validate_epub(b"this is not a zip file")
    assert any("not a valid zip file" in i.message for i in issues)


def test_missing_mimetype_entry_is_flagged(storage: LocalDiskStorage):
    broken = _rewrite_zip(_valid_epub_bytes(storage), lambda name, data: None if name == "mimetype" else data)
    issues = validate_epub(broken)
    assert any("mimetype" in i.message and "first entry" in i.message for i in issues)


def test_wrong_mimetype_content_is_flagged(storage: LocalDiskStorage):
    broken = _rewrite_zip(
        _valid_epub_bytes(storage), lambda name, data: b"text/plain" if name == "mimetype" else data
    )
    issues = validate_epub(broken)
    assert any("mimetype" in i.message and "must be exactly" in i.message for i in issues)


def test_missing_container_xml_is_flagged(storage: LocalDiskStorage):
    broken = _rewrite_zip(
        _valid_epub_bytes(storage), lambda name, data: None if name == "META-INF/container.xml" else data
    )
    issues = validate_epub(broken)
    assert any("missing META-INF/container.xml" in i.message for i in issues)


def test_malformed_container_xml_is_flagged(storage: LocalDiskStorage):
    broken = _rewrite_zip(
        _valid_epub_bytes(storage),
        lambda name, data: b"<not><valid" if name == "META-INF/container.xml" else data,
    )
    issues = validate_epub(broken)
    assert any("not valid XML" in i.message for i in issues)


def test_container_pointing_to_a_missing_opf_is_flagged(storage: LocalDiskStorage):
    def transform(name, data):
        if name == "META-INF/container.xml":
            return data.replace(b".opf", b"-does-not-exist.opf")
        return data

    broken = _rewrite_zip(_valid_epub_bytes(storage), transform)
    issues = validate_epub(broken)
    assert any("points to missing OPF" in i.message for i in issues)


def test_opf_missing_dc_identifier_is_flagged(storage: LocalDiskStorage):
    valid = _valid_epub_bytes(storage)
    opf_name = next(n for n in zipfile.ZipFile(io.BytesIO(valid)).namelist() if n.endswith(".opf"))

    def transform(name, data):
        if name != opf_name:
            return data
        root = ET.fromstring(data)
        ns = "{http://purl.org/dc/elements/1.1/}"
        metadata = root.find("{http://www.idpf.org/2007/opf}metadata")
        for el in list(metadata):
            if el.tag == f"{ns}identifier":
                metadata.remove(el)
        return ET.tostring(root)

    broken = _rewrite_zip(valid, transform)
    issues = validate_epub(broken)
    assert any("missing dc:identifier" in i.message for i in issues)


def test_manifest_item_pointing_to_a_missing_file_is_flagged(storage: LocalDiskStorage):
    valid = _valid_epub_bytes(storage)
    asset_name = next(n for n in zipfile.ZipFile(io.BytesIO(valid)).namelist() if n.endswith("asset-1.png"))
    broken = _rewrite_zip(valid, lambda name, data: None if name == asset_name else data)
    issues = validate_epub(broken)
    assert any("references missing file" in i.message for i in issues)


def test_img_src_not_in_manifest_is_flagged(storage: LocalDiskStorage):
    valid = _valid_epub_bytes(storage)
    content_name = next(
        n for n in zipfile.ZipFile(io.BytesIO(valid)).namelist() if n.endswith(".xhtml") and "nav" not in n
    )

    def transform(name, data):
        if name != content_name:
            return data
        return data.replace(b"assets/asset-1.png", b"assets/does-not-exist.png")

    broken = _rewrite_zip(valid, transform)
    issues = validate_epub(broken)
    assert any("is not a manifest-referenced file" in i.message for i in issues)


def test_removing_the_nav_document_is_flagged(storage: LocalDiskStorage):
    valid = _valid_epub_bytes(storage)
    opf_name = next(n for n in zipfile.ZipFile(io.BytesIO(valid)).namelist() if n.endswith(".opf"))

    def transform(name, data):
        if name != opf_name:
            return data
        return data.replace(b'properties="nav"', b"")

    broken = _rewrite_zip(valid, transform)
    issues = validate_epub(broken)
    assert any("no EPUB3 nav document" in i.message for i in issues)
