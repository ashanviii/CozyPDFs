from abc import ABC, abstractmethod
from typing import BinaryIO


class StorageBackend(ABC):
    """Every read/write of book/asset bytes goes through this interface —
    no code outside a StorageBackend implementation may touch a filesystem
    path or an object-storage client directly. That's what lets local disk
    (V1) become S3-compatible storage (R2/B2/S3) later as a config change
    instead of a rewrite of the conversion pipeline or the API.
    """

    @abstractmethod
    def put(
        self, key: str, data: bytes | BinaryIO, content_type: str = "application/octet-stream"
    ) -> None: ...

    @abstractmethod
    def get(self, key: str) -> bytes: ...

    @abstractmethod
    def get_url(self, key: str, expires_in: int | None = None) -> str:
        """A URL the client can fetch `key` from. Local: an app-served
        static path. Remote: a presigned URL, valid for `expires_in`
        seconds if given."""
        ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def delete_prefix(self, prefix: str) -> None:
        """Removes everything stored under `prefix` — the primitive book
        deletion/cleanup is built on."""
        ...
