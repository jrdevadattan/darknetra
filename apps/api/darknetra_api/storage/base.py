from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO, Protocol


class ObjectStoreError(RuntimeError):
    """Base class for fail-closed object-store failures."""


class ObjectDigestMismatch(ObjectStoreError):
    """The streamed bytes do not match the caller-provided expected digest."""


class ObjectKeyError(ObjectStoreError, ValueError):
    """An object key does not match the content-addressed key grammar."""


@dataclass(frozen=True, slots=True)
class StoredObject:
    object_key: str
    sha256: str
    size_bytes: int
    created: bool


class ObjectStore(Protocol):
    def put_verified(
        self, stream: BinaryIO, expected_sha256: str | None = None
    ) -> StoredObject: ...

    def open(self, object_key: str) -> BinaryIO: ...

    def verify(self, object_key: str, expected_sha256: str) -> bool: ...
