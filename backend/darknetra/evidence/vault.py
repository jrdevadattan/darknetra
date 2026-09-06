"""Content addressed local vault. Names never derive from uploaded filenames."""

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from darknetra.errors import TooLarge


@dataclass(frozen=True)
class StoredBlob:
    sha256: str
    size: int
    tmp_path: Path


class LocalVault:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str) -> Path:
        if not re.fullmatch(r"[0-9a-f-]{36}/[0-9a-f]{2}/[0-9a-f]{64}", key):
            raise ValueError("Invalid vault key")
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Invalid vault path")
        return path

    async def put_stream(self, stream, *, max_bytes: int) -> StoredBlob:
        fd, name = tempfile.mkstemp(dir=self.root, prefix="ingest-")
        path = Path(name)
        digest, size = hashlib.sha256(), 0
        try:
            with os.fdopen(fd, "wb") as out:
                async for chunk in stream:
                    size += len(chunk)
                    if size > max_bytes:
                        raise TooLarge("Upload exceeds limit")
                    digest.update(chunk)
                    out.write(chunk)
            return StoredBlob(digest.hexdigest(), size, path)
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    async def commit(self, blob: StoredBlob, key: str) -> None:
        path = self.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # Exclusive creation never replaces an existing original.
            with path.open("xb") as dest, blob.tmp_path.open("rb") as source:
                while chunk := source.read(65536):
                    dest.write(chunk)
        except FileExistsError:
            if self.hash(key) != blob.sha256:
                raise ValueError("Vault integrity mismatch") from None
        finally:
            blob.tmp_path.unlink(missing_ok=True)
        path.chmod(0o444)
        manifest = path.with_suffix(".manifest.json")
        if not manifest.exists():
            manifest.write_text(
                json.dumps({"sha256": blob.sha256, "size": blob.size}), encoding="utf-8"
            )

    def hash(self, key: str) -> str:
        with self.open(key) as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    def open(self, key: str):
        return self.path_for(key).open("rb")

    def exists(self, key: str) -> bool:
        return self.path_for(key).is_file()

    async def put_bytes(self, case_id, data: bytes) -> str:
        async def stream():
            yield data

        blob = await self.put_stream(stream(), max_bytes=max(1, len(data)))
        key = f"{case_id}/{blob.sha256[:2]}/{blob.sha256}"
        await self.commit(blob, key)
        return key
