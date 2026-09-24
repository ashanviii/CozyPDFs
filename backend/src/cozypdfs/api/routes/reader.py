from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from cozypdfs.api.deps import get_current_owner_id, get_db, get_storage
from cozypdfs.api.schemas import ProgressIn, ProgressOut
from cozypdfs.domain import books, reader
from cozypdfs.domain.errors import NotFoundError
from cozypdfs.reader_artifact.schema import ReaderArtifact
from cozypdfs.storage.base import StorageBackend

router = APIRouter(tags=["reader"])


@router.get("/books/{book_id}/reader-artifact", response_model=ReaderArtifact)
def get_reader_artifact(
    book_id: str,
    owner_id: str = Depends(get_current_owner_id),
    db: Session = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
) -> ReaderArtifact:
    book = books.get_owned_book(db, book_id, owner_id)
    return reader.get_reader_artifact(db, storage, book)


@router.get("/books/{book_id}/assets/{asset_id}")
def get_asset(
    book_id: str,
    asset_id: str,
    owner_id: str = Depends(get_current_owner_id),
    db: Session = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
) -> Response:
    """Streams one reader asset's bytes through an ownership check —
    deliberately not a static-file mount over the storage root, which would
    make every book's source PDF, DIR, and EPUB directly guessable/fetchable
    by anyone with a storage key, private books included."""
    book = books.get_owned_book(db, book_id, owner_id)
    data, media_type = reader.get_asset(db, storage, book, asset_id)
    return Response(content=data, media_type=media_type, headers={"Cache-Control": "private, max-age=3600"})


@router.get("/books/{book_id}/progress", response_model=ProgressOut)
def get_progress(
    book_id: str, owner_id: str = Depends(get_current_owner_id), db: Session = Depends(get_db)
) -> ProgressOut:
    book = books.get_owned_book(db, book_id, owner_id)
    progress = reader.get_progress(db, book, owner_id)
    if progress is None:
        raise NotFoundError(f"no reading progress saved for book {book_id!r}")
    return ProgressOut.from_model(progress)


@router.put("/books/{book_id}/progress", response_model=ProgressOut)
def save_progress(
    book_id: str,
    payload: ProgressIn,
    owner_id: str = Depends(get_current_owner_id),
    db: Session = Depends(get_db),
) -> ProgressOut:
    book = books.get_owned_book(db, book_id, owner_id)
    progress = reader.save_progress(
        db,
        book,
        owner_id,
        chapter_id=payload.chapter_id,
        block_id=payload.block_id,
        character_offset=payload.character_offset,
        mode=payload.mode,
    )
    return ProgressOut.from_model(progress)
