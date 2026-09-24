"""Structural EPUB validation.

No EPUB validator (EPUBCheck, which requires a JVM) is available in this
environment, so this is a hand-written structural validator, NOT a
substitute for full EPUBCheck compliance — it does not check every rule in
the EPUB3 specification (e.g. it does not validate XHTML against the full
EPUB content-document schema, does not check OPF/NCX against their XSDs,
and does not check accessibility metadata). What it does check, concretely:

  - the zip container: `mimetype` is present, first, uncompressed, and
    exactly "application/epub+zip"
  - META-INF/container.xml exists, parses, and points to an OPF that
    actually exists in the zip
  - the OPF parses as XML and has the required identifier/title/language
    metadata
  - every manifest item's href resolves to a real zip entry
  - every spine itemref references a real manifest id
  - an EPUB3 nav document is present (properties="nav")
  - every `<img src="...">` in every XHTML content document resolves to a
    manifest-referenced file

If a real EPUBCheck becomes available in a later phase, it should run
alongside (or instead of) this, not be presented as equivalent to it.
"""

import io
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree as ET

_OPF_NS = "{http://www.idpf.org/2007/opf}"
_XHTML_NS = "{http://www.w3.org/1999/xhtml}"


class EpubValidationError(Exception):
    pass


@dataclass
class ValidationIssue:
    message: str


def validate(epub_bytes: bytes) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    try:
        zf = zipfile.ZipFile(io.BytesIO(epub_bytes))
    except zipfile.BadZipFile:
        return [ValidationIssue("not a valid zip file")]

    if zf.testzip() is not None:
        issues.append(ValidationIssue("zip contains a corrupted member"))

    names = zf.namelist()
    issues.extend(_validate_mimetype(zf, names))

    opf_path = _validate_container(zf, names, issues)
    if opf_path is None:
        return issues

    manifest_hrefs, spine_idrefs, has_nav = _validate_opf(zf, opf_path, issues)
    opf_dir = opf_path.rsplit("/", 1)[0] + "/" if "/" in opf_path else ""

    for href, item_id in manifest_hrefs.items():
        resolved = opf_dir + href
        if resolved not in names:
            issues.append(ValidationIssue(f"manifest item {item_id!r} references missing file {resolved!r}"))

    manifest_ids = set(manifest_hrefs.values())
    for idref in spine_idrefs:
        if idref not in manifest_ids:
            issues.append(ValidationIssue(f"spine references missing manifest id {idref!r}"))

    if not has_nav:
        issues.append(ValidationIssue("no EPUB3 nav document (manifest item with properties=\"nav\")"))

    _validate_content_asset_references(zf, names, opf_dir, manifest_hrefs, issues)

    return issues


def _validate_mimetype(zf: zipfile.ZipFile, names: list[str]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not names or names[0] != "mimetype":
        issues.append(ValidationIssue("'mimetype' must be the first entry in the zip"))
        return issues
    info = zf.getinfo("mimetype")
    if info.compress_type != zipfile.ZIP_STORED:
        issues.append(ValidationIssue("'mimetype' must be stored uncompressed"))
    if zf.read("mimetype") != b"application/epub+zip":
        issues.append(ValidationIssue("'mimetype' content must be exactly 'application/epub+zip'"))
    return issues


def _validate_container(zf: zipfile.ZipFile, names: list[str], issues: list[ValidationIssue]) -> str | None:
    if "META-INF/container.xml" not in names:
        issues.append(ValidationIssue("missing META-INF/container.xml"))
        return None
    try:
        root = ET.fromstring(zf.read("META-INF/container.xml"))
    except ET.ParseError as exc:
        issues.append(ValidationIssue(f"META-INF/container.xml is not valid XML: {exc}"))
        return None

    rootfile = root.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")
    if rootfile is None:
        issues.append(ValidationIssue("container.xml has no <rootfile>"))
        return None
    opf_path = rootfile.get("full-path")
    if not opf_path or opf_path not in names:
        issues.append(ValidationIssue(f"container.xml points to missing OPF {opf_path!r}"))
        return None
    return opf_path


def _validate_opf(
    zf: zipfile.ZipFile, opf_path: str, issues: list[ValidationIssue]
) -> tuple[dict[str, str], list[str], bool]:
    try:
        root = ET.fromstring(zf.read(opf_path))
    except ET.ParseError as exc:
        issues.append(ValidationIssue(f"OPF is not valid XML: {exc}"))
        return {}, [], False

    metadata = root.find(f"{_OPF_NS}metadata")
    dc = "{http://purl.org/dc/elements/1.1/}"
    if metadata is None or metadata.find(f"{dc}identifier") is None:
        issues.append(ValidationIssue("OPF metadata is missing dc:identifier"))
    if metadata is None or metadata.find(f"{dc}title") is None:
        issues.append(ValidationIssue("OPF metadata is missing dc:title"))
    if metadata is None or metadata.find(f"{dc}language") is None:
        issues.append(ValidationIssue("OPF metadata is missing dc:language"))

    manifest_hrefs: dict[str, str] = {}
    has_nav = False
    manifest = root.find(f"{_OPF_NS}manifest")
    if manifest is None:
        issues.append(ValidationIssue("OPF has no <manifest>"))
    else:
        for item in manifest.findall(f"{_OPF_NS}item"):
            href = item.get("href")
            item_id = item.get("id")
            if not href or not item_id:
                issues.append(ValidationIssue("manifest item missing href or id"))
                continue
            manifest_hrefs[href] = item_id
            if "nav" in (item.get("properties") or "").split():
                has_nav = True

    spine_idrefs: list[str] = []
    spine = root.find(f"{_OPF_NS}spine")
    if spine is None:
        issues.append(ValidationIssue("OPF has no <spine>"))
    else:
        for itemref in spine.findall(f"{_OPF_NS}itemref"):
            idref = itemref.get("idref")
            if idref:
                spine_idrefs.append(idref)

    return manifest_hrefs, spine_idrefs, has_nav


def _validate_content_asset_references(
    zf: zipfile.ZipFile,
    names: list[str],
    opf_dir: str,
    manifest_hrefs: dict[str, str],
    issues: list[ValidationIssue],
) -> None:
    manifest_files = {opf_dir + href for href in manifest_hrefs}
    for href in manifest_hrefs:
        if not href.endswith((".xhtml", ".html")):
            continue
        path = opf_dir + href
        if path not in names:
            continue
        try:
            root = ET.fromstring(zf.read(path))
        except ET.ParseError as exc:
            issues.append(ValidationIssue(f"content document {path!r} is not valid XML: {exc}"))
            continue
        content_dir = path.rsplit("/", 1)[0] + "/" if "/" in path else ""
        for img in root.iter(f"{_XHTML_NS}img"):
            src = img.get("src")
            if not src:
                issues.append(ValidationIssue(f"{path}: <img> with no src"))
                continue
            resolved = _resolve_relative(content_dir, src)
            if resolved not in manifest_files:
                issues.append(ValidationIssue(f"{path}: <img src={src!r}> is not a manifest-referenced file"))


def _resolve_relative(base_dir: str, href: str) -> str:
    if not base_dir:
        return href
    parts = (base_dir + href).split("/")
    resolved: list[str] = []
    for part in parts:
        if part == "..":
            if resolved:
                resolved.pop()
        elif part and part != ".":
            resolved.append(part)
    return "/".join(resolved)


def validate_or_raise(epub_bytes: bytes) -> None:
    issues = validate(epub_bytes)
    if issues:
        raise EpubValidationError("; ".join(issue.message for issue in issues))
