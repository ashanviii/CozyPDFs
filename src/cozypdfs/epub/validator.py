"""Stage 8: EPUB validation.

Re-opens the written .epub as a plain zip and checks it independently of
ebooklib's own bookkeeping: mimetype framing, container.xml -> OPF
resolution, manifest/spine/nav integrity, every referenced file actually
present, every content document well-formed, and -- since the whole
pipeline started from untrusted PDF input -- a safety scan for `<script>`
elements, `on*` event-handler attributes, and `javascript:` URIs.

If this reports failures, the book must not be added to the library
(see `EpubValidationError`) rather than being silently accepted broken.
"""

from __future__ import annotations

import posixpath
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

_OPF_NS = "http://www.idpf.org/2007/opf"
_DC_NS = "http://purl.org/dc/elements/1.1/"
_XHTML_NS = "http://www.w3.org/1999/xhtml"
_CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"

_JS_SCHEME = "javascript:"


@dataclass(slots=True)
class ValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class DefaultEpubValidator:
    """`EpubValidator` implementation."""

    def validate(self, epub_path: Path) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        try:
            with zipfile.ZipFile(Path(epub_path), "r") as zf:
                _check_mimetype(zf, errors)
                names = set(zf.namelist())

                opf_path = _check_container(zf, errors)
                if opf_path is None:
                    return ValidationResult(False, errors, warnings)

                opf_root = _parse_xml(zf, opf_path, errors, "OPF")
                if opf_root is None:
                    return ValidationResult(False, errors, warnings)

                opf_dir = posixpath.dirname(opf_path)
                manifest = _check_metadata_and_manifest(opf_root, opf_dir, names, errors)
                _check_spine(opf_root, manifest, errors)
                _check_nav(opf_root, opf_dir, names, errors, zf)
                _check_content_documents(zf, manifest, opf_dir, names, errors)
        except zipfile.BadZipFile as exc:
            errors.append(f"Not a valid zip archive: {exc}")
        except Exception as exc:  # validation must never itself crash the pipeline
            errors.append(f"Unexpected error during validation: {exc}")

        return ValidationResult(is_valid=not errors, errors=errors, warnings=warnings)


def _check_mimetype(zf: zipfile.ZipFile, errors: list[str]) -> None:
    infos = zf.infolist()
    if not infos or infos[0].filename != "mimetype":
        errors.append("'mimetype' must be the first entry in the zip.")
        return
    if infos[0].compress_type != zipfile.ZIP_STORED:
        errors.append("'mimetype' entry must be stored uncompressed.")
    content = zf.read("mimetype")
    if content != b"application/epub+zip":
        errors.append(f"'mimetype' content is {content!r}, expected b'application/epub+zip'.")


def _check_container(zf: zipfile.ZipFile, errors: list[str]) -> str | None:
    if "META-INF/container.xml" not in zf.namelist():
        errors.append("Missing META-INF/container.xml.")
        return None
    root = _parse_xml(zf, "META-INF/container.xml", errors, "container.xml")
    if root is None:
        return None
    rootfile = root.find(f".//{{{_CONTAINER_NS}}}rootfile")
    if rootfile is None:
        errors.append("container.xml has no <rootfile> element.")
        return None
    opf_path = rootfile.get("full-path")
    if not opf_path or opf_path not in zf.namelist():
        errors.append(f"container.xml points to a missing OPF file: {opf_path!r}")
        return None
    return opf_path


def _parse_xml(zf: zipfile.ZipFile, name: str, errors: list[str], label: str):
    try:
        data = zf.read(name)
    except KeyError:
        errors.append(f"{label}: file not found in archive: {name}")
        return None
    try:
        return etree.fromstring(data)
    except etree.XMLSyntaxError as exc:
        errors.append(f"{label}: not well-formed XML ({exc}).")
        return None


def _check_metadata_and_manifest(
    opf_root, opf_dir: str, names: set[str], errors: list[str]
) -> dict[str, str]:
    metadata = opf_root.find(f"{{{_OPF_NS}}}metadata")
    if metadata is None:
        errors.append("OPF is missing <metadata>.")
    else:
        title = metadata.find(f"{{{_DC_NS}}}title")
        if title is None or not (title.text or "").strip():
            errors.append("OPF metadata is missing a non-empty dc:title.")
        language = metadata.find(f"{{{_DC_NS}}}language")
        if language is None or not (language.text or "").strip():
            errors.append("OPF metadata is missing dc:language.")

    manifest: dict[str, str] = {}
    manifest_el = opf_root.find(f"{{{_OPF_NS}}}manifest")
    if manifest_el is None:
        errors.append("OPF is missing <manifest>.")
        return manifest

    items = manifest_el.findall(f"{{{_OPF_NS}}}item")
    if not items:
        errors.append("OPF manifest has no items.")
    for item in items:
        item_id, href = item.get("id"), item.get("href")
        if not item_id or not href:
            errors.append("A manifest item is missing an id or href.")
            continue
        manifest[item_id] = href
        if _resolve(opf_dir, href) not in names:
            errors.append(f"Manifest item '{item_id}' references a missing file: {href}")
    return manifest


def _check_spine(opf_root, manifest: dict[str, str], errors: list[str]) -> None:
    spine_el = opf_root.find(f"{{{_OPF_NS}}}spine")
    if spine_el is None:
        errors.append("OPF is missing <spine>.")
        return
    itemrefs = spine_el.findall(f"{{{_OPF_NS}}}itemref")
    if not itemrefs:
        errors.append("OPF spine has no itemref entries.")
    for itemref in itemrefs:
        idref = itemref.get("idref")
        if not idref or idref not in manifest:
            errors.append(f"Spine itemref references an unknown manifest id: {idref!r}")


def _check_nav(
    opf_root, opf_dir: str, names: set[str], errors: list[str], zf: zipfile.ZipFile
) -> None:
    manifest_el = opf_root.find(f"{{{_OPF_NS}}}manifest")
    nav_href = None
    if manifest_el is not None:
        for item in manifest_el.findall(f"{{{_OPF_NS}}}item"):
            if "nav" in (item.get("properties") or "").split():
                nav_href = item.get("href")
                break

    if nav_href is None:
        errors.append("No EPUB3 nav document declared in the manifest (properties='nav').")
        return

    nav_path = _resolve(opf_dir, nav_href)
    if nav_path not in names:
        errors.append(f"Nav document is missing from the archive: {nav_path}")
        return

    root = _parse_xml(zf, nav_path, errors, "Nav document")
    if root is None:
        return
    nav_dir = posixpath.dirname(nav_path)
    for a in root.iter(f"{{{_XHTML_NS}}}a"):
        href = a.get("href")
        target = (href or "").split("#", 1)[0]
        if target and _resolve(nav_dir, target) not in names:
            errors.append(f"Nav document links to a missing file: {href}")


def _check_content_documents(
    zf: zipfile.ZipFile, manifest: dict[str, str], opf_dir: str, names: set[str], errors: list[str]
) -> None:
    for item_id, href in manifest.items():
        if not href.endswith((".xhtml", ".html", ".htm")):
            continue
        path = _resolve(opf_dir, href)
        if path not in names:
            continue  # already reported as a missing manifest reference
        root = _parse_xml(zf, path, errors, f"Content document '{href}'")
        if root is None:
            continue
        _check_document_safety(root, href, errors)
        _check_document_references(root, path, names, href, errors)


def _check_document_safety(root, href: str, errors: list[str]) -> None:
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue  # skip comments/PIs
        if etree.QName(el).localname.lower() == "script":
            errors.append(f"{href}: contains a <script> element, which is not allowed.")
        for attr, value in el.attrib.items():
            local = etree.QName(attr).localname if "}" in attr else attr
            if local.lower().startswith("on") and len(local) > 2:
                errors.append(f"{href}: unsafe event-handler attribute '{local}'.")
            if value.strip().lower().startswith(_JS_SCHEME):
                errors.append(f"{href}: attribute '{local}' uses a javascript: URI.")


def _check_document_references(root, doc_path: str, names: set[str], href: str, errors: list[str]) -> None:
    """Every same-package resource a content document points to must exist.

    Checks both <img src> and <link href> (stylesheets): a broken
    stylesheet link doesn't throw an XML error, doesn't fail EPUB
    structural checks, and just silently renders unstyled -- the kind of
    bug that only a real browser load surfaces, which is exactly why this
    check exists here instead.
    """
    doc_dir = posixpath.dirname(doc_path)

    for img in root.iter(f"{{{_XHTML_NS}}}img"):
        src = img.get("src")
        if not src:
            errors.append(f"{href}: <img> is missing a src attribute.")
        elif _resolve(doc_dir, src) not in names:
            errors.append(f"{href}: <img> references a missing file: {src}")

    for link in root.iter(f"{{{_XHTML_NS}}}link"):
        link_href = link.get("href")
        rel = (link.get("rel") or "").split()
        if link_href and "stylesheet" in rel and _resolve(doc_dir, link_href) not in names:
            errors.append(f"{href}: <link rel=\"stylesheet\"> references a missing file: {link_href}")


def _resolve(base_dir: str, href: str) -> str:
    return posixpath.normpath(posixpath.join(base_dir, href)) if base_dir else posixpath.normpath(href)
