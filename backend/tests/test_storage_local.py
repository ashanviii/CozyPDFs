import pytest

from cozypdfs.storage.local import LocalDiskStorage


def test_put_get_roundtrip(storage: LocalDiskStorage):
    storage.put("books/1/source.pdf", b"hello world")
    assert storage.get("books/1/source.pdf") == b"hello world"


def test_exists(storage: LocalDiskStorage):
    assert not storage.exists("books/1/source.pdf")
    storage.put("books/1/source.pdf", b"data")
    assert storage.exists("books/1/source.pdf")


def test_delete(storage: LocalDiskStorage):
    storage.put("books/1/source.pdf", b"data")
    storage.delete("books/1/source.pdf")
    assert not storage.exists("books/1/source.pdf")


def test_delete_prefix_removes_directory(storage: LocalDiskStorage):
    storage.put("books/1/source.pdf", b"data")
    storage.put("books/1/dir/v1.json", b"{}")
    storage.put("books/2/source.pdf", b"other book")

    storage.delete_prefix("books/1")

    assert not storage.exists("books/1/source.pdf")
    assert not storage.exists("books/1/dir/v1.json")
    assert storage.exists("books/2/source.pdf")


def test_get_url_is_stable_and_relative_to_base(storage: LocalDiskStorage):
    assert storage.get_url("books/1/source.pdf") == f"{storage.base_url}/books/1/source.pdf"


def test_rejects_keys_that_escape_root(storage: LocalDiskStorage):
    with pytest.raises(ValueError):
        storage.put("../escape.txt", b"nope")
