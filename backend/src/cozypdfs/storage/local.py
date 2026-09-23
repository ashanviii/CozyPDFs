import shutil
from pathlib import Path
from typing import BinaryIO

from cozypdfs.storage.base import StorageBackend


class LocalDiskStorage(StorageBackend):
    """Dev/V1 implementation: everything lives under `root` on local disk.
    `get_url` returns an app-served path rather than a presigned URL — the
    API mounts `storage_local_base_url` as a static route to it.
    """

    def __init__(self, root: str | Path, base_url: str = "/storage"):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.base_url = base_url.rstrip("/")

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if path != self.root and self.root not in path.parents:
            raise ValueError(f"storage key escapes root: {key!r}")
        return path

    def put(
        self, key: str, data: bytes | BinaryIO, content_type: str = "application/octet-stream"
    ) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, (bytes, bytearray)):
            path.write_bytes(data)
        else:
            with path.open("wb") as f:
                shutil.copyfileobj(data, f)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def get_url(self, key: str, expires_in: int | None = None) -> str:
        return f"{self.base_url}/{key}"

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    def delete_prefix(self, prefix: str) -> None:
        path = self._path(prefix)
        if not path.exists():
            return
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
