from __future__ import annotations

import hashlib
import io
import os
import stat
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from darknetra_api.storage.base import (
    ObjectHashMismatchError,
    ObjectIntegrityError,
    ObjectKeyError,
    ObjectStoreConfigurationError,
)
from darknetra_api.storage.local import LocalObjectStore
from hypothesis import given
from hypothesis import strategies as st

CONTENT = b"immutable evidence bytes\x00\xff"
CONTENT_SHA256 = "284fb46ce634608584003203463b1657bfba79f4def7f73b91b4e06ddd59a563"
CONTENT_KEY = "sha256/28/4f/284fb46ce634608584003203463b1657bfba79f4def7f73b91b4e06ddd59a563"


def _staging_entries(root: Path) -> list[Path]:
    return list((root / ".staging").iterdir())


def test_put_verified_returns_deterministic_key_digest_and_byte_count(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path, chunk_size=4)

    stored = store.put_verified(io.BytesIO(CONTENT))

    assert stored.object_key == CONTENT_KEY
    assert stored.sha256 == CONTENT_SHA256
    assert stored.size_bytes == len(CONTENT)
    assert not hasattr(stored, "staging_path")


@given(st.binary(max_size=256 * 1024))
def test_arbitrary_bytes_round_trip_by_content_digest(payload: bytes) -> None:
    with tempfile.TemporaryDirectory() as directory:
        store = LocalObjectStore(directory)
        expected = hashlib.sha256(payload).hexdigest()

        stored = store.put_verified(io.BytesIO(payload), expected_sha256=expected)

        assert stored.object_key == f"sha256/{expected[:2]}/{expected[2:4]}/{expected}"
        assert stored.sha256 == expected
        assert stored.size_bytes == len(payload)
        with store.open(stored.object_key) as saved:
            assert saved.read() == payload
        assert store.verify(stored.object_key, expected)


def test_duplicate_content_deduplicates_without_replacing_final_file(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    first = store.put_verified(io.BytesIO(CONTENT))
    final_path = tmp_path / Path(first.object_key)
    first_inode = final_path.stat().st_ino

    second = store.put_verified(io.BytesIO(CONTENT))

    assert second == first
    assert final_path.stat().st_ino == first_inode
    assert _staging_entries(tmp_path) == []


def test_concurrent_same_content_writers_share_one_valid_object(tmp_path: Path) -> None:
    stores = [LocalObjectStore(tmp_path, chunk_size=7) for _ in range(8)]
    barrier = threading.Barrier(8)

    def put(store: LocalObjectStore) -> object:
        barrier.wait()
        return store.put_verified(io.BytesIO(CONTENT * 1000))

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(put, store) for store in stores]
        results = [future.result(timeout=10) for future in futures]

    assert len(set(results)) == 1
    with stores[0].open(results[0].object_key) as saved:
        assert saved.read() == CONTENT * 1000
    assert _staging_entries(tmp_path) == []


def test_hash_mismatch_removes_owned_stage_and_creates_no_final(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    wrong_digest = "0" * 64

    with pytest.raises(ObjectHashMismatchError, match="expected SHA-256 does not match"):
        store.put_verified(io.BytesIO(CONTENT), expected_sha256=wrong_digest)

    assert _staging_entries(tmp_path) == []
    assert not (tmp_path / "sha256").exists()


class _FailingStream:
    def __init__(self) -> None:
        self._calls = 0

    def read(self, size: int = -1) -> bytes:
        assert 0 < size <= 8
        self._calls += 1
        if self._calls == 1:
            return b"partial"
        raise OSError("injected read failure")


def test_partial_read_failure_cleans_staging(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path, chunk_size=8)

    with pytest.raises(OSError, match="injected read failure"):
        store.put_verified(_FailingStream())

    assert _staging_entries(tmp_path) == []
    assert not (tmp_path / "sha256").exists()


def test_partial_write_failure_cleans_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalObjectStore(tmp_path, chunk_size=4)
    real_write = store._write_chunk
    calls = 0

    def fail_after_first_chunk(file_object: object, chunk: bytes) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected write failure")
        real_write(file_object, chunk)

    monkeypatch.setattr(store, "_write_chunk", fail_after_first_chunk)

    with pytest.raises(OSError, match="injected write failure"):
        store.put_verified(io.BytesIO(b"123456789"), expected_sha256=None)

    assert _staging_entries(tmp_path) == []
    assert not (tmp_path / "sha256").exists()


def test_promotion_failure_cleans_stage_without_deleting_existing_final(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = LocalObjectStore(tmp_path)
    existing = store.put_verified(io.BytesIO(CONTENT))
    existing_path = tmp_path / Path(existing.object_key)
    other = b"different bytes"
    real_replace = os.replace

    def fail_other_promotion(
        source: object, destination: object, *args: object, **kwargs: object
    ) -> None:
        destination_path = (
            Path(destination) if isinstance(destination, (str, os.PathLike)) else None
        )
        if destination_path is not None and destination_path != existing_path:
            raise OSError("injected promotion failure")
        real_replace(source, destination, *args, **kwargs)

    monkeypatch.setattr(os, "replace", fail_other_promotion)

    with pytest.raises(OSError, match="injected promotion failure"):
        store.put_verified(io.BytesIO(other))

    assert _staging_entries(tmp_path) == []
    assert existing_path.read_bytes() == CONTENT
    other_digest = hashlib.sha256(other).hexdigest()
    assert not (tmp_path / f"sha256/{other_digest[:2]}/{other_digest[2:4]}/{other_digest}").exists()


def test_final_object_is_not_visible_before_atomic_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = LocalObjectStore(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    real_replace = os.replace

    def paused_replace(
        source: object, destination: object, *args: object, **kwargs: object
    ) -> None:
        entered.set()
        assert release.wait(timeout=5)
        real_replace(source, destination, *args, **kwargs)

    monkeypatch.setattr(os, "replace", paused_replace)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(store.put_verified, io.BytesIO(CONTENT))
        assert entered.wait(timeout=5)
        assert not (tmp_path / Path(CONTENT_KEY)).exists()
        release.set()
        future.result(timeout=5)

    assert (tmp_path / Path(CONTENT_KEY)).read_bytes() == CONTENT


@pytest.mark.parametrize(
    "object_key",
    [
        "",
        "/sha256/95/a3/" + CONTENT_SHA256,
        "../sha256/95/a3/" + CONTENT_SHA256,
        "sha256/../a3/" + CONTENT_SHA256,
        "sha256\\95\\a3\\" + CONTENT_SHA256,
        "SHA256/95/a3/" + CONTENT_SHA256,
        "sha256/95/a3/" + CONTENT_SHA256.upper(),
        "sha256/94/a3/" + CONTENT_SHA256,
        "sha256/95/a4/" + CONTENT_SHA256,
        "sha512/95/a3/" + CONTENT_SHA256,
        "sha256/95/a3/" + CONTENT_SHA256[:-1],
        "sha256/95/a3/" + CONTENT_SHA256 + "x",
        "sha256/95/a3/" + CONTENT_SHA256 + "\x00",
        "sha256/95/a3/" + CONTENT_SHA256[:-1] + "é",
        "sha256/⁹⁵/a3/" + CONTENT_SHA256,
    ],
)
def test_open_and_verify_reject_noncanonical_keys(tmp_path: Path, object_key: str) -> None:
    store = LocalObjectStore(tmp_path)

    with pytest.raises(ObjectKeyError, match="canonical content key"):
        store.open(object_key)
    with pytest.raises(ObjectKeyError, match="canonical content key"):
        store.verify(object_key, CONTENT_SHA256)


def test_symlinked_digest_directory_cannot_escape_root(tmp_path: Path) -> None:
    if not hasattr(os, "symlink"):
        pytest.skip("symlinks are not supported")
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (tmp_path / "sha256").mkdir()
    try:
        (tmp_path / "sha256" / CONTENT_SHA256[:2]).symlink_to(
            outside,
            target_is_directory=True,
        )
    except OSError as exc:
        pytest.skip(f"symlinks unavailable to this account: {exc}")
    store = LocalObjectStore(tmp_path)

    with pytest.raises(ObjectStoreConfigurationError, match="symlink|reparse"):
        store.put_verified(io.BytesIO(CONTENT))

    assert list(outside.iterdir()) == []
    assert _staging_entries(tmp_path) == []


def test_replaced_root_symlink_cannot_redirect_a_later_write(tmp_path: Path) -> None:
    if not hasattr(os, "symlink"):
        pytest.skip("symlinks are not supported")
    root = tmp_path / "evidence"
    store = LocalObjectStore(root)
    original_root = tmp_path / "original-root"
    root.rename(original_root)
    outside = tmp_path / "outside"
    (outside / ".staging").mkdir(parents=True)
    (outside / ".locks").mkdir()
    try:
        root.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable to this account: {exc}")

    with pytest.raises(ObjectStoreConfigurationError, match="symlink|reparse"):
        store.put_verified(io.BytesIO(CONTENT))

    assert list(outside.rglob("*.tmp")) == []
    assert not (outside / "sha256").exists()


def test_open_round_trip_and_verify_reports_tamper_without_rewriting(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    stored = store.put_verified(io.BytesIO(CONTENT))
    final_path = tmp_path / Path(stored.object_key)
    final_path.chmod(0o644)
    final_path.write_bytes(b"X" + CONTENT[1:])

    assert not store.verify(stored.object_key, stored.sha256)
    assert final_path.read_bytes() == b"X" + CONTENT[1:]
    with pytest.raises(ObjectIntegrityError, match="does not match its content key"):
        store.put_verified(io.BytesIO(CONTENT))


def test_final_file_is_read_only_on_posix(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    stored = store.put_verified(io.BytesIO(CONTENT))

    mode = stat.S_IMODE((tmp_path / Path(stored.object_key)).stat().st_mode)
    if os.name == "posix":
        assert mode == 0o444
    else:
        assert not os.access(tmp_path / Path(stored.object_key), os.W_OK)


def test_root_must_be_a_real_writable_directory(tmp_path: Path) -> None:
    root_file = tmp_path / "not-a-directory"
    root_file.write_text("x", encoding="utf-8")

    with pytest.raises(ObjectStoreConfigurationError, match="directory"):
        LocalObjectStore(root_file)


def test_configured_root_cannot_be_a_symlink_or_reparse_point(tmp_path: Path) -> None:
    if not hasattr(os, "symlink"):
        pytest.skip("symlinks are not supported")
    actual = tmp_path / "actual"
    actual.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(actual, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable to this account: {exc}")

    with pytest.raises(ObjectStoreConfigurationError, match="symlink|reparse"):
        LocalObjectStore(linked)


def test_configured_root_cannot_descend_from_a_symlink_or_reparse_point(
    tmp_path: Path,
) -> None:
    if not hasattr(os, "symlink"):
        pytest.skip("symlinks are not supported")
    actual = tmp_path / "actual"
    actual.mkdir()
    linked_parent = tmp_path / "linked-parent"
    try:
        linked_parent.symlink_to(actual, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable to this account: {exc}")

    with pytest.raises(ObjectStoreConfigurationError, match="symlink|reparse"):
        LocalObjectStore(linked_parent / "evidence")


def test_initialization_probes_that_staging_is_writable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_open = os.open

    def reject_probe(path: object, *args: object, **kwargs: object) -> int:
        if Path(path).name.startswith(".write-probe-"):
            raise PermissionError("injected read-only volume")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", reject_probe)

    with pytest.raises(ObjectStoreConfigurationError, match="not writable"):
        LocalObjectStore(tmp_path)


def test_linux_uses_directory_descriptors_for_symlink_safe_operations(tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("secure dir_fd operations are a Linux/POSIX contract")

    assert LocalObjectStore(tmp_path)._supports_secure_dir_fd


def test_new_content_directories_are_fsynced_before_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = LocalObjectStore(tmp_path)
    if os.name != "posix":
        pytest.skip("directory fsync is a POSIX durability contract")
    calls = 0
    real_fsync = os.fsync

    def record_fsync(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", record_fsync)

    store.put_verified(io.BytesIO(CONTENT))

    # Two staged-file syncs, three newly-created shard parent syncs, one promotion sync.
    assert calls >= 6


def test_staging_and_final_directories_must_share_root_filesystem(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    store._root_device += 1

    with pytest.raises(ObjectStoreConfigurationError, match="share one filesystem"):
        store.put_verified(io.BytesIO(CONTENT))

    assert _staging_entries(tmp_path) == []


def test_expected_digest_must_be_canonical(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)

    with pytest.raises(ObjectKeyError, match="canonical SHA-256"):
        store.put_verified(io.BytesIO(CONTENT), expected_sha256=CONTENT_SHA256.upper())
