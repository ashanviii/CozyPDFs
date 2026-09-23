from fastapi.testclient import TestClient

from cozypdfs.config import Settings
from cozypdfs.domain import books
from tests.factories import make_pdf_bytes


def _upload(
    client: TestClient,
    *,
    filename: str = "book.pdf",
    pages: int = 1,
    title=None,
    author=None,
    data: bytes | None = None,
):
    data = data if data is not None else make_pdf_bytes(pages=pages, title=title, author=author)
    return client.post("/api/books", files={"file": (filename, data, "application/pdf")})


def test_upload_returns_created_book(client: TestClient):
    response = _upload(client, title="My Book", author="Author")

    assert response.status_code == 201
    body = response.json()
    assert body["reused"] is False
    assert body["book"]["status"] == "preparing"
    assert body["book"]["title"] == "My Book"
    assert body["book"]["author"] == "Author"
    assert "source_storage_key" not in body["book"]
    assert "dir_storage_key" not in body["book"]


def test_uploaded_book_appears_in_library_listing(client: TestClient):
    _upload(client)

    response = client.get("/api/books")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_invalid_file_upload_is_rejected(client: TestClient):
    response = client.post(
        "/api/books", files={"file": ("not.pdf", b"not a pdf", "application/pdf")}
    )

    assert response.status_code == 422


def test_duplicate_upload_reuses_book(client: TestClient):
    data = make_pdf_bytes()
    first = _upload(client, filename="a.pdf", data=data)
    second = _upload(client, filename="a-again.pdf", data=data)

    assert second.status_code == 200
    assert second.json()["reused"] is True
    assert second.json()["book"]["id"] == first.json()["book"]["id"]

    listing = client.get("/api/books")
    assert len(listing.json()) == 1


def test_oversized_upload_returns_413(app, client: TestClient):
    app.state.settings = Settings(cookie_secret="test-secret", max_upload_size_mb=0)

    response = _upload(client)

    assert response.status_code == 413


def test_too_many_pages_returns_422(app, client: TestClient):
    app.state.settings = Settings(cookie_secret="test-secret", max_page_count=1)

    response = _upload(client, pages=3)

    assert response.status_code == 422


def test_get_book_status(client: TestClient):
    book_id = _upload(client).json()["book"]["id"]

    response = client.get(f"/api/books/{book_id}")

    assert response.status_code == 200
    assert response.json()["id"] == book_id


def test_get_missing_book_returns_404(client: TestClient):
    response = client.get("/api/books/does-not-exist")
    assert response.status_code == 404


def test_ownership_isolation_on_get(app):
    client_a = TestClient(app)
    client_b = TestClient(app)
    book_id = _upload(client_a).json()["book"]["id"]

    response = client_b.get(f"/api/books/{book_id}")

    assert response.status_code == 404


def test_ownership_isolation_on_listing(app):
    client_a = TestClient(app)
    client_b = TestClient(app)
    _upload(client_a)

    response = client_b.get("/api/books")

    assert response.status_code == 200
    assert response.json() == []


def test_retry_requires_failed_status(client: TestClient):
    book_id = _upload(client).json()["book"]["id"]

    response = client.post(f"/api/books/{book_id}/retry")

    assert response.status_code == 409


def test_retry_via_api_after_a_failure(app, client: TestClient, database):
    book_id = _upload(client).json()["book"]["id"]

    session = database.create_session()
    books.mark_failed(session, book_id, "boom")
    session.commit()
    session.close()

    response = client.post(f"/api/books/{book_id}/retry")

    assert response.status_code == 200
    assert response.json()["status"] == "preparing"
    assert response.json()["error_message"] is None


def test_ownership_isolation_on_retry(app):
    client_a = TestClient(app)
    client_b = TestClient(app)
    book_id = _upload(client_a).json()["book"]["id"]

    response = client_b.post(f"/api/books/{book_id}/retry")

    assert response.status_code == 404


def test_delete_book_removes_it_from_library(client: TestClient):
    book_id = _upload(client).json()["book"]["id"]

    response = client.delete(f"/api/books/{book_id}")

    assert response.status_code == 204
    assert client.get("/api/books").json() == []


def test_ownership_isolation_on_delete(app):
    client_a = TestClient(app)
    client_b = TestClient(app)
    book_id = _upload(client_a).json()["book"]["id"]

    response = client_b.delete(f"/api/books/{book_id}")

    assert response.status_code == 404
    assert len(client_a.get("/api/books").json()) == 1
