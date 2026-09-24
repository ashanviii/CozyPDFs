"""Phase 2C reader API: reader-artifact fetch, asset streaming, and
reading-progress persistence — all ownership-checked the same way as the
existing book routes (see test_api_books.py's isolation tests)."""

from pathlib import Path

from fastapi.testclient import TestClient

from cozypdfs.db.session import Database
from cozypdfs.jobs.worker import run_once
from cozypdfs.storage.local import LocalDiskStorage
from tests.factories import make_pdf_bytes

GOLDEN_DIR = Path(__file__).parent / "golden_pdfs"


def _upload(client: TestClient, *, data: bytes | None = None) -> str:
    data = data if data is not None else make_pdf_bytes()
    response = client.post("/api/books", files={"file": ("book.pdf", data, "application/pdf")})
    return response.json()["book"]["id"]


def _upload_and_convert(
    client: TestClient, database: Database, storage: LocalDiskStorage, *, pdf_name: str = "equations"
) -> str:
    data = (GOLDEN_DIR / f"{pdf_name}.pdf").read_bytes()
    book_id = _upload(client, data=data)
    processed = run_once(database.create_session, storage)
    assert processed is True
    return book_id


def test_reader_artifact_404_before_conversion_finishes(client: TestClient):
    book_id = _upload(client)
    response = client.get(f"/api/books/{book_id}/reader-artifact")
    assert response.status_code == 404


def test_reader_artifact_404_for_missing_book(client: TestClient):
    response = client.get("/api/books/does-not-exist/reader-artifact")
    assert response.status_code == 404


def test_reader_artifact_returns_a_valid_artifact_once_ready(
    client: TestClient, database: Database, storage: LocalDiskStorage
):
    book_id = _upload_and_convert(client, database, storage, pdf_name="single_column_prose")

    response = client.get(f"/api/books/{book_id}/reader-artifact")

    assert response.status_code == 200
    body = response.json()
    assert body["book_id"] == book_id
    assert body["sections"]
    assert any(block["type"] == "paragraph" for section in body["sections"] for block in section["blocks"])


def test_ownership_isolation_on_reader_artifact(app, database: Database, storage: LocalDiskStorage):
    client_a = TestClient(app)
    client_b = TestClient(app)
    book_id = _upload_and_convert(client_a, database, storage, pdf_name="single_column_prose")

    response = client_b.get(f"/api/books/{book_id}/reader-artifact")
    assert response.status_code == 404


def test_asset_endpoint_streams_the_actual_image_bytes(
    client: TestClient, database: Database, storage: LocalDiskStorage
):
    book_id = _upload_and_convert(client, database, storage, pdf_name="equations")
    artifact = client.get(f"/api/books/{book_id}/reader-artifact").json()
    asset_id = artifact["assets"][0]["id"]

    response = client.get(f"/api/books/{book_id}/assets/{asset_id}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert len(response.content) > 0


def test_asset_endpoint_404_for_unknown_asset_id(
    client: TestClient, database: Database, storage: LocalDiskStorage
):
    book_id = _upload_and_convert(client, database, storage, pdf_name="equations")
    response = client.get(f"/api/books/{book_id}/assets/does-not-exist")
    assert response.status_code == 404


def test_ownership_isolation_on_assets(app, database: Database, storage: LocalDiskStorage):
    client_a = TestClient(app)
    client_b = TestClient(app)
    book_id = _upload_and_convert(client_a, database, storage, pdf_name="equations")
    artifact = client_a.get(f"/api/books/{book_id}/reader-artifact").json()
    asset_id = artifact["assets"][0]["id"]

    response = client_b.get(f"/api/books/{book_id}/assets/{asset_id}")
    assert response.status_code == 404


def test_progress_404_when_none_saved(client: TestClient):
    book_id = _upload(client)
    response = client.get(f"/api/books/{book_id}/progress")
    assert response.status_code == 404


def test_progress_round_trip(client: TestClient):
    book_id = _upload(client)

    put_response = client.put(
        f"/api/books/{book_id}/progress",
        json={"chapter_id": "ch0", "block_id": "b3", "character_offset": 42, "mode": "scroll"},
    )
    assert put_response.status_code == 200
    assert put_response.json()["block_id"] == "b3"

    get_response = client.get(f"/api/books/{book_id}/progress")
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["chapter_id"] == "ch0"
    assert body["block_id"] == "b3"
    assert body["character_offset"] == 42
    assert body["mode"] == "scroll"


def test_progress_put_upserts_not_duplicates(client: TestClient):
    book_id = _upload(client)

    client.put(
        f"/api/books/{book_id}/progress",
        json={"chapter_id": "ch0", "block_id": "b1", "character_offset": 0, "mode": "scroll"},
    )
    second = client.put(
        f"/api/books/{book_id}/progress",
        json={"chapter_id": "ch0", "block_id": "b9", "character_offset": 5, "mode": "paginated"},
    )
    assert second.status_code == 200

    get_response = client.get(f"/api/books/{book_id}/progress")
    assert get_response.json()["block_id"] == "b9"
    assert get_response.json()["mode"] == "paginated"


def test_progress_rejects_an_unknown_mode(client: TestClient):
    book_id = _upload(client)
    response = client.put(
        f"/api/books/{book_id}/progress",
        json={"chapter_id": "ch0", "block_id": "b1", "character_offset": 0, "mode": "flip-book"},
    )
    assert response.status_code == 422


def test_progress_rejects_a_negative_character_offset(client: TestClient):
    book_id = _upload(client)
    response = client.put(
        f"/api/books/{book_id}/progress",
        json={"chapter_id": "ch0", "block_id": "b1", "character_offset": -1, "mode": "scroll"},
    )
    assert response.status_code == 422


def test_ownership_isolation_on_progress(app):
    client_a = TestClient(app)
    client_b = TestClient(app)
    book_id = _upload(client_a)

    client_a.put(
        f"/api/books/{book_id}/progress",
        json={"chapter_id": "ch0", "block_id": "b1", "character_offset": 0, "mode": "scroll"},
    )

    get_response = client_b.get(f"/api/books/{book_id}/progress")
    assert get_response.status_code == 404

    put_response = client_b.put(
        f"/api/books/{book_id}/progress",
        json={"chapter_id": "ch0", "block_id": "b1", "character_offset": 0, "mode": "scroll"},
    )
    assert put_response.status_code == 404
