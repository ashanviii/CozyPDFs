from fastapi import APIRouter, Depends, Response, UploadFile
from sqlalchemy.orm import Session

from cozypdfs.api.deps import get_app_settings, get_current_owner_id, get_db, get_storage
from cozypdfs.api.schemas import BookOut, UploadResponse
from cozypdfs.config import Settings
from cozypdfs.domain import books, uploads
from cozypdfs.domain.uploads import FileTooLargeError
from cozypdfs.storage.base import StorageBackend

router = APIRouter(tags=["books"])


async def _read_limited(file: UploadFile, max_bytes: int) -> bytes:
    """Aborts as soon as the cap is exceeded instead of buffering an
    arbitrarily large upload fully into memory just to reject it."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise FileTooLargeError(f"file exceeds {max_bytes} byte limit")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/books", response_model=UploadResponse)
async def upload_book(
    response: Response,
    file: UploadFile,
    owner_id: str = Depends(get_current_owner_id),
    db: Session = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
    settings: Settings = Depends(get_app_settings),
) -> UploadResponse:
    data = await _read_limited(file, settings.max_upload_size_mb * 1024 * 1024)

    result = uploads.upload_pdf(
        db,
        storage,
        settings,
        owner_id=owner_id,
        filename=file.filename or "upload.pdf",
        data=data,
    )

    response.status_code = 200 if result.reused else 201
    return UploadResponse(book=BookOut.from_model(result.book), reused=result.reused)


@router.get("/books", response_model=list[BookOut])
def list_books(
    owner_id: str = Depends(get_current_owner_id), db: Session = Depends(get_db)
) -> list[BookOut]:
    return [BookOut.from_model(book) for book in books.list_books_for_owner(db, owner_id)]


@router.get("/books/{book_id}", response_model=BookOut)
def get_book_status(
    book_id: str, owner_id: str = Depends(get_current_owner_id), db: Session = Depends(get_db)
) -> BookOut:
    book = books.get_owned_book(db, book_id, owner_id)
    return BookOut.from_model(book)


@router.post("/books/{book_id}/retry", response_model=BookOut)
def retry_book(
    book_id: str, owner_id: str = Depends(get_current_owner_id), db: Session = Depends(get_db)
) -> BookOut:
    book = books.get_owned_book(db, book_id, owner_id)
    books.retry_book(db, book)
    return BookOut.from_model(book)


@router.delete("/books/{book_id}", status_code=204)
def delete_book(
    book_id: str,
    owner_id: str = Depends(get_current_owner_id),
    db: Session = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
) -> Response:
    book = books.get_owned_book(db, book_id, owner_id)
    books.delete_book(db, storage, book)
    return Response(status_code=204)
