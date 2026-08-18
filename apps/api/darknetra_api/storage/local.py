from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import BinaryIO

from darknetra_api.storage.base import (
    ObjectDigestMismatch,
    ObjectKeyError,
    StoredObject,
)

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_KEY = re.compile(r"^sha256/([0-9a-f]{2})/([0-9a-f]{2})/([0-9a-f]{64})$")
_CHUNK_SIZE = 1024 * 1024


class LocalObjectStore:
    """Content-addressed storage with verified staging and atomic promotion."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.staging = self.root / ".staging"
        self.staging.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _key_for_digest(digest: str) -> str:
        return f"sha256/{digest[:2]}/{digest[2:4]}/{digest}"

    @staticmethod
    def _validate_digest(value: str) -> str:
        if not isinstance(value, str) or not _DIGEST.fullmatch(value):
            raise ObjectKeyError("SHA-256 digest must be 64 lowercase hexadecimal characters")
        return value

    @staticmethod
    def _validate_key(object_key: str) -> tuple[str, str]:
        if not isinstance(object_key, str):
            raise ObjectKeyError("object key is invalid")
        match = _KEY.fullmatch(object_key)
        if match is None:
            raise ObjectKeyError("object key is invalid")
        first, second, digest = match.groups()
        if first != digest[:2] or second != digest[2:4]:
            raise ObjectKeyError("object key digest prefixes do not match")
        return object_key, digest

    def _path_for_key(self, object_key: str) -> Path:
        safe_key, _ = self._validate_key(object_key)
        return self.root.joinpath(*safe_key.split("/"))

    def put_verified(
        self, stream: BinaryIO, expected_sha256: str | None = None
    ) -> StoredObject:
        if expected_sha256 is not None:
            self._validate_digest(expected_sha256)

        hasher = hashlib.sha256()
        size_bytes = 0
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix="upload-",
                dir=self.staging,
                delete=False,
            ) as staged:
                temporary_path = Path(staged.name)
                while True:
                    chunk = stream.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    if not isinstance(chunk, bytes):
                        raise TypeError("object-store stream must return bytes")
                    hasher.update(chunk)
                    size_bytes += len(chunk)
                    staged.write(chunk)
                staged.flush()
                os.fsync(staged.fileno())

            digest = hasher.hexdigest()
            if expected_sha256 is not None and digest != expected_sha256:
                raise ObjectDigestMismatch("streamed object did not match expected SHA-256")

            object_key = self._key_for_digest(digest)
            destination = self._path_for_key(object_key)
            destination.parent.mkdir(parents=True, exist_ok=True)

            if destination.exists():
                temporary_path.unlink(missing_ok=True)
                temporary_path = None
                if not self.verify(object_key, digest):
                    raise ObjectDigestMismatch(
                        "existing content-addressed object failed digest verification"
                    )
                return StoredObject(
                    object_key=object_key,
                    sha256=digest,
                    size_bytes=size_bytes,
                    created=False,
                )

            os.replace(temporary_path, destination)
            temporary_path = None
            os.chmod(destination, 0o444)
            self._fsync_directory(destination.parent)
            return StoredObject(
                object_key=object_key,
                sha256=digest,
                size_bytes=size_bytes,
                created=True,
            )
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def open(self, object_key: str) -> BinaryIO:
        return self._path_for_key(object_key).open("rb")

    def verify(self, object_key: str, expected_sha256: str) -> bool:
        _, digest_from_key = self._validate_key(object_key)
        expected = self._validate_digest(expected_sha256)
        if digest_from_key != expected:
            return False
        path = self._path_for_key(object_key)
        try:
            handle = path.open("rb")
        except FileNotFoundError:
            return False
        hasher = hashlib.sha256()
        with handle:
            while True:
                chunk = handle.read(_CHUNK_SIZE)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest() == expected

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            flags |= os.O_DIRECTORY
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
