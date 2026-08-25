from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import BinaryIO


class ObjectStoreError(Exception):
    """Base error for object-store failures."""


class ObjectStoreConfigurationError(ObjectStoreError):
    """The configured store cannot provide the required safety properties."""


class ObjectKeyError(ValueError, ObjectStoreError):
    """A caller supplied a non-canonical content key or digest."""


class ObjectHashMismatchError(ObjectStoreError):
    """A stream's observed SHA-256 did not match the caller's expectation."""

    def __init__(self, *, expected_sha256: str, observed_sha256: str) -> None:
        super().__init__("expected SHA-256 does not match streamed content")
        self.expected_sha256 = expected_sha256
        self.observed_sha256 = observed_sha256


class ObjectIntegrityError(ObjectStoreError):
    """A content-addressed final object does not match its key."""


@dataclass(frozen=True, slots=True)
class StoredObject:
    object_key: str
    sha256: str
    size_bytes: int


class ObjectStore(ABC):
    @abstractmethod
    def put_verified(
        self,
        stream: BinaryIO,
        expected_sha256: str | None = None,
    ) -> StoredObject:
        """Stream, hash, durably store, and return a content-addressed object."""

    @abstractmethod
    def open(self, object_key: str) -> BinaryIO:
        """Open an existing object for binary reading."""

    @abstractmethod
    def verify(self, object_key: str, expected_sha256: str) -> bool:
        """Stream an object and compare it with an expected canonical digest."""
