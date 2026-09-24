"""ReaderArtifact -> a standards-compliant EPUB3 file, via ebooklib.

ebooklib owns the container/OPF/NCX/nav format entirely — there is no
reason to hand-roll the EPUB container format when a maintained library
already does it correctly. This module's own job is narrow: feed ebooklib
deterministic content (fetching each asset's bytes from StorageBackend,
since a ReaderAsset only carries a deterministic filename, never a storage
path — see reader_artifact/schema.py) and neutralize the two places
ebooklib itself introduces wall-clock time — the OPF's required
`dcterms:modified` metadata (via the `mtime` write option) and the zip
container's per-entry timestamps (via `_normalize_zip_timestamps`) — since
neither reflects anything meaningful yet (Phase 2B doesn't track a real
"last modified" concept) and both would otherwise be the only source of
non-determinism in an identical build.
"""

import io
import zipfile
from datetime import UTC, datetime

from ebooklib import epub

from cozypdfs.epub.xhtml import render_section_document
from cozypdfs.reader_artifact.schema import NavigationItem, ReaderArtifact
from cozypdfs.storage.base import StorageBackend

_STYLESHEET = b"""\
body { font-family: Georgia, "Times New Roman", serif; line-height: 1.6; margin: 1.2em; color: #1f2320; }
h1, h2, h3, h4, h5, h6 { font-family: -apple-system, sans-serif; line-height: 1.3; }
p { margin: 0 0 1em; }
ul, ol { margin: 0 0 1em; }
figure { margin: 1.2em 0; text-align: center; }
figure img { max-width: 100%; }
figcaption { font-size: 0.85em; font-style: italic; color: #555; margin-top: 0.4em; }
table { border-collapse: collapse; margin: 1em 0; }
table th, table td { border: 1px solid #ccc; padding: 0.4em 0.7em; text-align: left; }
table th { background: #f5f3ee; }
aside { font-size: 0.85em; color: #555; border-left: 2px solid #ccc; padding-left: 0.75em; }
"""

_FIXED_ZIP_DATE = (1980, 1, 1, 0, 0, 0)
_FIXED_MTIME = datetime(1980, 1, 1, tzinfo=UTC)


def build_epub(artifact: ReaderArtifact, *, storage: StorageBackend, asset_storage_keys: dict[str, str]) -> bytes:
    book = epub.EpubBook()
    book.set_identifier(f"cozypdfs-book-{artifact.book_id}")
    book.set_title(artifact.meta.title or "Untitled")
    book.set_language(artifact.meta.language or "en")
    if artifact.meta.author:
        book.add_author(artifact.meta.author)

    style_item = epub.EpubItem(uid="style", file_name="style/style.css", media_type="text/css", content=_STYLESHEET)
    book.add_item(style_item)

    for asset in artifact.assets:
        storage_key = asset_storage_keys[asset.id]
        image_item = epub.EpubImage(
            uid=asset.id,
            file_name=f"assets/{asset.filename}",
            media_type=asset.media_type,
            content=storage.get(storage_key),
        )
        book.add_item(image_item)

    section_items = []
    for section in artifact.sections:
        xhtml = render_section_document(section, stylesheet_href="style/style.css")
        item = epub.EpubHtml(
            title=section.title or "Untitled",
            file_name=f"{section.id}.xhtml",
            lang=artifact.meta.language or "en",
            content=xhtml,
        )
        item.add_item(style_item)
        book.add_item(item)
        section_items.append(item)

    book.toc = tuple(_toc_entry(item, chapter_file=f"{item.section_id}.xhtml") for item in artifact.navigation)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *section_items]

    buffer = io.BytesIO()
    epub.write_epub(buffer, book, {"mtime": _FIXED_MTIME})
    return _normalize_zip_timestamps(buffer.getvalue())


def _toc_entry(item: NavigationItem, chapter_file: str, *, is_top: bool = True):
    href = chapter_file if is_top else f"{chapter_file}#{item.section_id}"
    link = epub.Link(href, item.title, item.section_id)
    if not item.children:
        return link
    return (link, tuple(_toc_entry(child, chapter_file, is_top=False) for child in item.children))


def _normalize_zip_timestamps(data: bytes) -> bytes:
    """Rewrites every zip entry with a fixed date so identical logical
    content always produces byte-identical EPUB output — the only
    non-determinism ebooklib's own zip writing introduces is wall-clock
    per-entry timestamps."""
    source = zipfile.ZipFile(io.BytesIO(data))
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as out:
        for info in source.infolist():
            normalized = zipfile.ZipInfo(info.filename, date_time=_FIXED_ZIP_DATE)
            normalized.compress_type = info.compress_type
            normalized.external_attr = info.external_attr
            out.writestr(normalized, source.read(info.filename))
    return output.getvalue()
