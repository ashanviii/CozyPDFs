"""Phase 2C: serving the Phase 2B ReaderArtifact (and its assets) to the
live reader, and persisting reading position.

Every function here takes an already-ownership-checked `Book` (the same
pattern as domain/books.py's delete_book) — the API layer resolves
ownership once via `get_owned_book`, then everything downstream trusts it.
Raw storage keys never leave this module; routes only ever get back parsed
models or raw bytes.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from cozypdfs.db.models import Book, ReadingProgress
from cozypdfs.dir.schema import DIRDocument
from cozypdfs.domain.errors import NotFoundError
from cozypdfs.reader_artifact.schema import ReaderArtifact
from cozypdfs.storage.base import StorageBackend

# All reader assets are rendered/extracted as PNG today — see
# epub/build.py's own hardcoded _ASSET_MEDIA_TYPE. DIR's Asset model
# doesn't carry a media type, so this mirrors that existing assumption
# rather than inventing a new source of truth for it.
_ASSET_MEDIA_TYPE = "image/png"


def get_reader_artifact(db: Session, storage: StorageBackend, book: Book) -> ReaderArtifact:
    if book.reader_artifact_storage_key is None:
        raise NotFoundError(f"book {book.id!r} has no reader artifact yet")
    data = storage.get(book.reader_artifact_storage_key)
    return ReaderArtifact.model_validate_json(data)


def get_asset(db: Session, storage: StorageBackend, book: Book, asset_id: str) -> tuple[bytes, str]:
    """Resolves an asset id to its bytes via the book's DIR (the only place
    an asset's storage_key is recorded — see dir/schema.py's Asset model).
    Returns (bytes, media_type)."""
    if book.dir_storage_key is None:
        raise NotFoundError(f"book {book.id!r} has no assets yet")

    document = DIRDocument.model_validate_json(storage.get(book.dir_storage_key))
    asset = next((a for a in document.assets if a.id == asset_id), None)
    if asset is None:
        raise NotFoundError(f"asset {asset_id!r} not found on book {book.id!r}")

    return storage.get(asset.storage_key), _ASSET_MEDIA_TYPE


def get_progress(db: Session, book: Book, owner_id: str) -> ReadingProgress | None:
    stmt = select(ReadingProgress).where(
        ReadingProgress.book_id == book.id, ReadingProgress.owner_id == owner_id
    )
    return db.execute(stmt).scalar_one_or_none()


def save_progress(
    db: Session,
    book: Book,
    owner_id: str,
    *,
    chapter_id: str,
    block_id: str,
    character_offset: int,
    mode: str,
) -> ReadingProgress:
    progress = get_progress(db, book, owner_id)
    if progress is None:
        progress = ReadingProgress(book_id=book.id, owner_id=owner_id)
        db.add(progress)

    progress.chapter_id = chapter_id
    progress.block_id = block_id
    progress.character_offset = character_offset
    progress.mode = mode
    db.flush()
    return progress
