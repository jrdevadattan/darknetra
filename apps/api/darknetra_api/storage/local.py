from __future__ import annotations

import errno
import hashlib
import hmac
import os
import re
import secrets
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

from darknetra_api.storage.base import (
    ObjectHashMismatchError,
    ObjectIntegrityError,
    ObjectKeyError,
    ObjectStore,
    ObjectStoreConfigurationError,
    StoredObject,
)

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_CONTENT_KEY_PATTERN = re.compile(
    r"sha256/([0-9a-f]{2})/([0-9a-f]{2})/([0-9a-f]{64})\Z",
    re.ASCII,
)
_DEFAULT_CHUNK_SIZE = 1024 * 1024
_DIRECTORY_MODE = 0o755
_FINAL_FILE_MODE = 0o444
_LOCK_FILE_MODE = 0o600


class LocalObjectStore(ObjectStore):
    """Local content-addressed storage with same-filesystem atomic promotion.

    POSIX uses descriptor-relative traversal and rejects link substitution. Platforms
    without those primitives fail closed unless the caller explicitly opts into a trusted,
    stable development volume. That fallback rejects stable reparse points but cannot
    contain an active path substitution race.

    Read-only mode bits provide defense in depth. Content keys and streaming verification
    enforce integrity.
    """

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        chunk_size: int = _DEFAULT_CHUNK_SIZE,
        allow_trusted_volume_fallback: bool = False,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        configured_root = Path(root).expanduser().absolute()
        self.root = configured_root
        self._allow_trusted_volume_fallback = allow_trusted_volume_fallback
        if not self._supports_secure_dir_fd and not allow_trusted_volume_fallback:
            raise ObjectStoreConfigurationError(
                "secure descriptor traversal is unavailable; trusted-volume fallback "
                "requires explicit opt-in"
            )
        try:
            self._create_root_durably(configured_root)
        except OSError as exc:
            raise ObjectStoreConfigurationError(
                f"object-store root cannot be created as a directory: {configured_root}"
            ) from exc
        if not configured_root.is_dir():
            raise ObjectStoreConfigurationError(
                f"object-store root must be a directory: {configured_root}"
            )

        self.chunk_size = chunk_size
        try:
            root_result = self.root.stat()
            self._root_device = root_result.st_dev
            self._root_identity = (root_result.st_dev, root_result.st_ino)
            with self._directory((".staging",), create=True):
                pass
            with self._directory((".locks",), create=True):
                pass
            self._probe_writable()
        except ObjectStoreConfigurationError:
            raise
        except OSError as exc:
            raise ObjectStoreConfigurationError(
                f"object-store root is not writable: {configured_root}"
            ) from exc

    def put_verified(
        self,
        stream: BinaryIO,
        expected_sha256: str | None = None,
    ) -> StoredObject:
        if expected_sha256 is not None:
            self._validate_digest(expected_sha256)

        staging_name = f"{secrets.token_hex(24)}.tmp"
        staged = True
        digest = hashlib.sha256()
        size_bytes = 0

        with self._directory((".staging",), create=False) as (staging_fd, staging_path):
            try:
                with self._create_staging_file(
                    staging_fd, staging_path, staging_name
                ) as staged_file:
                    while True:
                        chunk = stream.read(self.chunk_size)
                        if chunk == b"":
                            break
                        if not isinstance(chunk, bytes):
                            raise TypeError("binary object stream must return bytes")
                        self._write_chunk(staged_file, chunk)
                        digest.update(chunk)
                        size_bytes += len(chunk)
                    staged_file.flush()
                    os.fsync(staged_file.fileno())
                    self._make_read_only(staged_file.fileno(), staging_path / staging_name)
                    os.fsync(staged_file.fileno())

                observed_sha256 = digest.hexdigest()
                if expected_sha256 is not None and not hmac.compare_digest(
                    observed_sha256,
                    expected_sha256,
                ):
                    raise ObjectHashMismatchError(
                        expected_sha256=expected_sha256,
                        observed_sha256=observed_sha256,
                    )

                object_key = self._key_for_digest(observed_sha256)
                with (
                    self._object_lock(observed_sha256),
                    self._directory(
                        ("sha256", observed_sha256[:2], observed_sha256[2:4]),
                        create=True,
                    ) as (final_fd, final_path),
                ):
                    if self._entry_exists(final_fd, final_path, observed_sha256):
                        if not self._verify_entry(
                            final_fd,
                            final_path,
                            observed_sha256,
                            observed_sha256,
                        ):
                            raise ObjectIntegrityError(
                                "existing object does not match its content key"
                            )
                    else:
                        self._replace(
                            staging_fd,
                            staging_path,
                            staging_name,
                            final_fd,
                            final_path,
                            observed_sha256,
                        )
                        staged = False
                        self._fsync_promotion_directories(
                            staging_fd,
                            staging_path,
                            final_fd,
                            final_path,
                        )

                return StoredObject(
                    object_key=object_key,
                    sha256=observed_sha256,
                    size_bytes=size_bytes,
                )
            finally:
                if staged:
                    self._unlink_owned_stage(staging_fd, staging_path, staging_name)

    def open(self, object_key: str) -> BinaryIO:
        digest = self._digest_from_key(object_key)
        with self._directory(
            ("sha256", digest[:2], digest[2:4]),
            create=False,
        ) as (directory_fd, directory_path):
            return self._open_entry(directory_fd, directory_path, digest)

    def verify(self, object_key: str, expected_sha256: str) -> bool:
        self._validate_digest(expected_sha256)
        digest = self._digest_from_key(object_key)
        if not hmac.compare_digest(expected_sha256, digest):
            return False
        with self._directory(
            ("sha256", digest[:2], digest[2:4]),
            create=False,
        ) as (directory_fd, directory_path):
            return self._verify_entry(directory_fd, directory_path, digest, digest)

    @staticmethod
    def _write_chunk(file_object: BinaryIO, chunk: bytes) -> None:
        remaining = memoryview(chunk)
        while remaining:
            written = file_object.write(remaining)
            if written is None or written <= 0:
                raise OSError("object-store staging write made no progress")
            remaining = remaining[written:]

    @staticmethod
    def _key_for_digest(digest: str) -> str:
        return f"sha256/{digest[:2]}/{digest[2:4]}/{digest}"

    @staticmethod
    def _validate_digest(digest: str) -> None:
        if not isinstance(digest, str) or _SHA256_PATTERN.fullmatch(digest) is None:
            raise ObjectKeyError("expected digest must be canonical SHA-256")

    @classmethod
    def _digest_from_key(cls, object_key: str) -> str:
        if not isinstance(object_key, str) or not object_key.isascii():
            raise ObjectKeyError("object key must use the canonical content key grammar")
        match = _CONTENT_KEY_PATTERN.fullmatch(object_key)
        if match is None:
            raise ObjectKeyError("object key must use the canonical content key grammar")
        first, second, digest = match.groups()
        if first != digest[:2] or second != digest[2:4]:
            raise ObjectKeyError("object key must use the canonical content key grammar")
        return digest

    @staticmethod
    def _is_reparse(stat_result: os.stat_result) -> bool:
        attributes = getattr(stat_result, "st_file_attributes", 0)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        return bool(attributes & reparse_flag)

    @classmethod
    def _reject_link(cls, path: Path) -> None:
        try:
            result = path.lstat()
        except FileNotFoundError:
            return
        if stat.S_ISLNK(result.st_mode) or cls._is_reparse(result):
            raise ObjectStoreConfigurationError(
                f"object-store path cannot contain a symlink or reparse point: {path}"
            )

    @classmethod
    def _reject_link_ancestors(cls, path: Path) -> None:
        candidate = path
        while True:
            cls._reject_link(candidate)
            if candidate.parent == candidate:
                return
            candidate = candidate.parent

    def _assert_root_identity(self) -> None:
        try:
            self._reject_link_ancestors(self.root)
            result = self.root.stat()
        except ObjectStoreConfigurationError:
            raise
        except OSError as exc:
            raise ObjectStoreConfigurationError(
                "object-store root is missing or inaccessible"
            ) from exc
        if (result.st_dev, result.st_ino) != self._root_identity:
            raise ObjectStoreConfigurationError("object-store root identity changed")

    def _create_root_durably(self, root: Path) -> None:
        if not self._supports_secure_dir_fd:
            self._reject_link_ancestors(root)
            root.mkdir(parents=True, exist_ok=True, mode=_DIRECTORY_MODE)
            self._reject_link_ancestors(root)
            return

        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        anchor = Path(root.anchor)
        descriptor = os.open(anchor, flags)
        try:
            for part in root.parts[1:]:
                try:
                    next_descriptor = os.open(part, flags, dir_fd=descriptor)
                except FileNotFoundError:
                    created = False
                    try:
                        os.mkdir(part, mode=_DIRECTORY_MODE, dir_fd=descriptor)
                        created = True
                    except FileExistsError:
                        pass
                    if created:
                        os.fsync(descriptor)
                    next_descriptor = os.open(part, flags, dir_fd=descriptor)
                except OSError as exc:
                    if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                        raise ObjectStoreConfigurationError(
                            "object-store root contains a symlink, reparse point, "
                            "or non-directory"
                        ) from exc
                    raise
                os.close(descriptor)
                descriptor = next_descriptor
        finally:
            os.close(descriptor)

    @property
    def _supports_secure_dir_fd(self) -> bool:
        return (
            os.name == "posix"
            and os.open in os.supports_dir_fd
            and os.mkdir in os.supports_dir_fd
            and os.rename in os.supports_dir_fd
            and os.unlink in os.supports_dir_fd
        )

    @contextmanager
    def _directory(
        self,
        parts: tuple[str, ...],
        *,
        create: bool,
    ) -> Iterator[tuple[int | None, Path]]:
        self._assert_root_identity()
        if self._supports_secure_dir_fd:
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
            try:
                descriptor = os.open(self.root, flags)
            except OSError as exc:
                raise ObjectStoreConfigurationError(
                    "object-store root contains a symlink, reparse point, or non-directory"
                ) from exc
            opened_root = os.fstat(descriptor)
            if (opened_root.st_dev, opened_root.st_ino) != self._root_identity:
                os.close(descriptor)
                raise ObjectStoreConfigurationError("object-store root identity changed")
            current_path = self.root
            try:
                for part in parts:
                    created = False
                    if create:
                        try:
                            os.mkdir(part, mode=_DIRECTORY_MODE, dir_fd=descriptor)
                            created = True
                        except FileExistsError:
                            pass
                    if created:
                        os.fsync(descriptor)
                    next_descriptor = os.open(part, flags, dir_fd=descriptor)
                    os.close(descriptor)
                    descriptor = next_descriptor
                    current_path /= part
                    self._require_same_filesystem(os.fstat(descriptor), current_path)
                yield descriptor, current_path
            except OSError as exc:
                if exc.errno in {getattr(os, "ELOOP", 40), getattr(os, "ENOTDIR", 20)}:
                    raise ObjectStoreConfigurationError(
                        f"object-store path contains a symlink, reparse point, or non-directory: {current_path}"
                    ) from exc
                raise
            finally:
                os.close(descriptor)
            return

        current_path = self.root
        for part in parts:
            parent_path = current_path
            current_path /= part
            created = False
            if create:
                try:
                    current_path.mkdir(mode=_DIRECTORY_MODE)
                    created = True
                except FileExistsError:
                    pass
            if created:
                self._fsync_directory(None, parent_path)
            self._reject_link(current_path)
            result = current_path.stat()
            if not stat.S_ISDIR(result.st_mode):
                raise ObjectStoreConfigurationError(
                    f"object-store path must be a directory: {current_path}"
                )
            self._require_same_filesystem(result, current_path)
        self._assert_root_identity()
        yield None, current_path

    def _probe_writable(self) -> None:
        probe_name = f".write-probe-{secrets.token_hex(16)}"
        with self._directory((".staging",), create=False) as (directory_fd, directory_path):
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            if directory_fd is not None:
                descriptor = os.open(probe_name, flags, 0o600, dir_fd=directory_fd)
            else:
                descriptor = os.open(directory_path / probe_name, flags, 0o600)
            try:
                os.write(descriptor, b"\0")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
                self._unlink_owned_stage(directory_fd, directory_path, probe_name)

    def _require_same_filesystem(self, result: os.stat_result, path: Path) -> None:
        if result.st_dev != self._root_device:
            raise ObjectStoreConfigurationError(
                f"object-store staging and final paths must share one filesystem: {path}"
            )

    @contextmanager
    def _create_staging_file(
        self,
        directory_fd: int | None,
        directory_path: Path,
        name: str,
    ) -> Iterator[BinaryIO]:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        if directory_fd is not None:
            descriptor = os.open(name, flags, 0o600, dir_fd=directory_fd)
        else:
            descriptor = os.open(directory_path / name, flags, 0o600)
        with os.fdopen(descriptor, "wb", buffering=0) as file_object:
            yield file_object

    @staticmethod
    def _make_read_only(descriptor: int, path: Path) -> None:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, _FINAL_FILE_MODE)
        else:  # pragma: no cover - Windows/Python builds without fchmod
            os.chmod(path, _FINAL_FILE_MODE)

    @contextmanager
    def _object_lock(self, digest: str) -> Iterator[None]:
        with self._directory((".locks",), create=False) as (directory_fd, directory_path):
            flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
            lock_name = f"{digest}.lock"
            if directory_fd is not None:
                descriptor = os.open(lock_name, flags, _LOCK_FILE_MODE, dir_fd=directory_fd)
            else:
                lock_path = directory_path / lock_name
                self._reject_link(lock_path)
                descriptor = os.open(lock_path, flags, _LOCK_FILE_MODE)
            try:
                self._lock_descriptor(descriptor)
                yield
            finally:
                self._unlock_descriptor(descriptor)
                os.close(descriptor)

    @staticmethod
    def _lock_descriptor(descriptor: int) -> None:
        if os.name == "posix":
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)
            return
        import msvcrt

        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"\0")
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)

    @staticmethod
    def _unlock_descriptor(descriptor: int) -> None:
        if os.name == "posix":
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_UN)
            return
        import msvcrt

        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)

    @staticmethod
    def _entry_exists(directory_fd: int | None, directory_path: Path, name: str) -> bool:
        try:
            if directory_fd is not None:
                os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            else:
                (directory_path / name).lstat()
        except FileNotFoundError:
            return False
        return True

    @staticmethod
    def _replace(
        staging_fd: int | None,
        staging_path: Path,
        staging_name: str,
        final_fd: int | None,
        final_path: Path,
        final_name: str,
    ) -> None:
        if staging_fd is not None and final_fd is not None:
            os.replace(
                staging_name,
                final_name,
                src_dir_fd=staging_fd,
                dst_dir_fd=final_fd,
            )
        else:
            os.replace(staging_path / staging_name, final_path / final_name)

    @staticmethod
    def _fsync_directory(directory_fd: int | None, directory_path: Path) -> None:
        if os.name != "posix":
            return
        if directory_fd is not None:
            os.fsync(directory_fd)
            return
        descriptor = os.open(directory_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _fsync_promotion_directories(
        self,
        staging_fd: int | None,
        staging_path: Path,
        final_fd: int | None,
        final_path: Path,
    ) -> None:
        source_error: OSError | None = None
        try:
            self._fsync_directory(staging_fd, staging_path)
        except OSError as exc:
            source_error = exc
        try:
            self._fsync_directory(final_fd, final_path)
        except OSError:
            if source_error is not None:
                raise source_error
            raise
        if source_error is not None:
            raise source_error

    def _unlink_owned_stage(
        self,
        directory_fd: int | None,
        directory_path: Path,
        name: str,
    ) -> None:
        removed = False
        try:
            if directory_fd is not None:
                os.unlink(name, dir_fd=directory_fd)
                removed = True
            else:
                stage_path = directory_path / name
                if os.name == "nt":
                    os.chmod(stage_path, stat.S_IWRITE)
                stage_path.unlink()
                removed = True
        except FileNotFoundError:
            pass
        if removed:
            self._fsync_directory(directory_fd, directory_path)

    def _open_entry(
        self,
        directory_fd: int | None,
        directory_path: Path,
        name: str,
    ) -> BinaryIO:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        if os.name == "posix":
            flags |= getattr(os, "O_NONBLOCK", 0)
        if directory_fd is not None:
            descriptor = os.open(name, flags, dir_fd=directory_fd)
        else:
            path = directory_path / name
            self._reject_link(path)
            descriptor = os.open(path, flags)
        result = os.fstat(descriptor)
        if not stat.S_ISREG(result.st_mode) or result.st_dev != self._root_device:
            os.close(descriptor)
            raise ObjectIntegrityError(
                "object-store key must resolve to a regular file on the local volume"
            )
        if result.st_nlink != 1:
            os.close(descriptor)
            raise ObjectIntegrityError("object-store final file has an unexpected hard link count")
        if os.name == "posix" and stat.S_IMODE(result.st_mode) != _FINAL_FILE_MODE:
            os.close(descriptor)
            raise ObjectIntegrityError("object-store final file does not have read-only mode 0444")
        return os.fdopen(descriptor, "rb", buffering=0)

    def _verify_entry(
        self,
        directory_fd: int | None,
        directory_path: Path,
        name: str,
        expected_sha256: str,
    ) -> bool:
        digest = hashlib.sha256()
        with self._open_entry(directory_fd, directory_path, name) as object_file:
            while True:
                chunk = object_file.read(self.chunk_size)
                if chunk == b"":
                    break
                digest.update(chunk)
        return hmac.compare_digest(digest.hexdigest(), expected_sha256)
