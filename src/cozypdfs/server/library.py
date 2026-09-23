"""Library storage.

After a successful conversion, the book must be automatically added to the
user's library -- no second upload, no re-parsing the PDF to show it
again. This is the `LibraryStore` sketched in `interfaces.py`, implemented
as plain files on disk: each book gets its own directory holding the
generated EPUB, the original source PDF (so "download EPUB" and "the user
owns their file" both hold even after a server restart), and a cover
image if one was detected. A single `index.json` holds the metadata the
library UI actually lists by (title, author, progress) so opening the
library never requires re-reading every EPUB.
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from ..models import Book

_MIME_TO_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/bmp": "bmp",
    "image/webp": "webp",
}
_VALID_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def is_valid_book_id(book_id: str) -> bool:
    """Server-generated ids are always a 32-char hex uuid4 -- reject anything
    else before it ever reaches a filesystem path."""
    return bool(_VALID_ID_RE.match(book_id))


@dataclass(slots=True)
class LibraryEntry:
    id: str
    title: str
    author: str | None
    chapter_count: int
    has_cover: bool
    created_at: str
    last_opened: str | None = None
    progress_cfi: str | None = None
    progress_percent: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


class FileSystemLibraryStore:
    """`LibraryStore` implementation: one directory per book plus an index."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.books_dir = self.root / "books"
        self.books_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self.root / "index.json"
        self._lock = Lock()
        self._entries: dict[str, LibraryEntry] = self._load_index()

    def _load_index(self) -> dict[str, LibraryEntry]:
        if not self._index_path.exists():
            return {}
        raw = json.loads(self._index_path.read_text(encoding="utf-8"))
        return {item["id"]: LibraryEntry(**item) for item in raw}

    def _save_index(self) -> None:
        data = [e.to_dict() for e in self._entries.values()]
        self._index_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add(self, book: Book, epub_path: Path, source_pdf_path: Path | None) -> str:
        book_id = uuid.uuid4().hex
        book_dir = self.books_dir / book_id
        book_dir.mkdir(parents=True, exist_ok=True)

        shutil.copyfile(epub_path, book_dir / "book.epub")
        if source_pdf_path is not None and Path(source_pdf_path).exists():
            shutil.copyfile(source_pdf_path, book_dir / "source.pdf")

        has_cover = False
        if book.cover is not None:
            ext = _MIME_TO_EXT.get(book.cover.mime_type, "png")
            (book_dir / f"cover.{ext}").write_bytes(book.cover.data)
            has_cover = True

        entry = LibraryEntry(
            id=book_id,
            title=book.metadata.title,
            author=book.metadata.author,
            chapter_count=len(book.chapters),
            has_cover=has_cover,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._entries[book_id] = entry
            self._save_index()
        return book_id

    def list(self) -> list[LibraryEntry]:
        with self._lock:
            return sorted(self._entries.values(), key=lambda e: e.created_at, reverse=True)

    def get(self, book_id: str) -> LibraryEntry | None:
        with self._lock:
            return self._entries.get(book_id)

    def epub_path(self, book_id: str) -> Path | None:
        if self.get(book_id) is None:
            return None
        path = self.books_dir / book_id / "book.epub"
        return path if path.exists() else None

    def source_pdf_path(self, book_id: str) -> Path | None:
        if self.get(book_id) is None:
            return None
        path = self.books_dir / book_id / "source.pdf"
        return path if path.exists() else None

    def cover_path(self, book_id: str) -> Path | None:
        entry = self.get(book_id)
        if entry is None or not entry.has_cover:
            return None
        for ext in _MIME_TO_EXT.values():
            path = self.books_dir / book_id / f"cover.{ext}"
            if path.exists():
                return path
        return None

    def update_progress(self, book_id: str, cfi: str | None, percent: float) -> bool:
        with self._lock:
            entry = self._entries.get(book_id)
            if entry is None:
                return False
            entry.progress_cfi = cfi
            entry.progress_percent = max(0.0, min(100.0, percent))
            entry.last_opened = datetime.now(timezone.utc).isoformat()
            self._save_index()
            return True

    def delete(self, book_id: str) -> bool:
        with self._lock:
            entry = self._entries.pop(book_id, None)
            if entry is None:
                return False
            self._save_index()
        shutil.rmtree(self.books_dir / book_id, ignore_errors=True)
        return True
