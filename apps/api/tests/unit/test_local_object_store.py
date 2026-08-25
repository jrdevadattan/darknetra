from __future__ import annotations

import hashlib
import io
import multiprocessing
import os
import signal
import stat
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

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


def _store(
    root: str | os.PathLike[str],
    *,
    chunk_size: int = 1024 * 1024,
) -> LocalObjectStore:
    return LocalObjectStore(
        root,
        chunk_size=chunk_size,
        allow_trusted_volume_fallback=True,
    )


def _process_put(
    root: str,
    payload: bytes,
    start: Any,
    results: Any,
) -> None:
    try:
        store = LocalObjectStore(root, allow_trusted_volume_fallback=True, chunk_size=97)
        start.wait(timeout=10)
        stored = store.put_verified(io.BytesIO(payload))
        results.put(("ok", stored.object_key))
    except Exception as exc:  # noqa: BLE001 - child must report every failure to parent
        results.put(("error", f"{type(exc).__name__}: {exc}"))


def test_put_verified_returns_deterministic_key_digest_and_byte_count(tmp_path: Path) -> None:
    store = _store(tmp_path, chunk_size=4)

    stored = store.put_verified(io.BytesIO(CONTENT))

    assert stored.object_key == CONTENT_KEY
    assert stored.sha256 == CONTENT_SHA256
    assert stored.size_bytes == len(CONTENT)
    assert not hasattr(stored, "staging_path")


@given(st.binary(max_size=256 * 1024))
def test_arbitrary_bytes_round_trip_by_content_digest(payload: bytes) -> None:
    with tempfile.TemporaryDirectory() as directory:
        store = _store(directory)
        expected = hashlib.sha256(payload).hexdigest()

        stored = store.put_verified(io.BytesIO(payload), expected_sha256=expected)

        assert stored.object_key == f"sha256/{expected[:2]}/{expected[2:4]}/{expected}"
        assert stored.sha256 == expected
        assert stored.size_bytes == len(payload)
        with store.open(stored.object_key) as saved:
            assert saved.read() == payload
        assert store.verify(stored.object_key, expected)


def test_duplicate_content_deduplicates_without_replacing_final_file(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = store.put_verified(io.BytesIO(CONTENT))
    final_path = tmp_path / Path(first.object_key)
    first_inode = final_path.stat().st_ino

    second = store.put_verified(io.BytesIO(CONTENT))

    assert second == first
    assert final_path.stat().st_ino == first_inode
    assert _staging_entries(tmp_path) == []


def test_concurrent_same_content_writers_share_one_valid_object(tmp_path: Path) -> None:
    stores = [_store(tmp_path, chunk_size=7) for _ in range(8)]
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


def test_multiple_processes_deduplicate_one_final_object(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    results = context.Queue()
    payload = CONTENT * 4096
    processes = [
        context.Process(
            target=_process_put,
            args=(str(tmp_path), payload, start, results),
        )
        for _ in range(6)
    ]
    for process in processes:
        process.start()
    start.set()
    try:
        for process in processes:
            process.join(timeout=20)
        assert all(not process.is_alive() for process in processes)
        assert all(process.exitcode == 0 for process in processes)
        observed = [results.get(timeout=2) for _ in processes]
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        results.close()

    assert {status for status, _ in observed} == {"ok"}
    assert len({key for _, key in observed}) == 1
    assert _staging_entries(tmp_path) == []
    final_files = [path for path in (tmp_path / "sha256").rglob("*") if path.is_file()]
    assert len(final_files) == 1


def test_hash_mismatch_removes_owned_stage_and_creates_no_final(tmp_path: Path) -> None:
    store = _store(tmp_path)
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
    store = _store(tmp_path, chunk_size=8)

    with pytest.raises(OSError, match="injected read failure"):
        store.put_verified(_FailingStream())

    assert _staging_entries(tmp_path) == []
    assert not (tmp_path / "sha256").exists()


def test_partial_write_failure_cleans_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _store(tmp_path, chunk_size=4)
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
    store = _store(tmp_path)
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
    store = _store(tmp_path)
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
    store = _store(tmp_path)

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
    store = _store(tmp_path)

    with pytest.raises(ObjectStoreConfigurationError, match="symlink|reparse"):
        store.put_verified(io.BytesIO(CONTENT))

    assert list(outside.iterdir()) == []
    assert _staging_entries(tmp_path) == []


def test_replaced_root_symlink_cannot_redirect_a_later_write(tmp_path: Path) -> None:
    if not hasattr(os, "symlink"):
        pytest.skip("symlinks are not supported")
    root = tmp_path / "evidence"
    store = _store(root)
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
    store = _store(tmp_path)
    stored = store.put_verified(io.BytesIO(CONTENT))
    final_path = tmp_path / Path(stored.object_key)
    final_path.chmod(0o644)
    final_path.write_bytes(b"X" + CONTENT[1:])
    final_path.chmod(0o444)

    assert not store.verify(stored.object_key, stored.sha256)
    assert final_path.read_bytes() == b"X" + CONTENT[1:]
    with pytest.raises(ObjectIntegrityError, match="does not match its content key"):
        store.put_verified(io.BytesIO(CONTENT))


def test_verify_binds_manifest_digest_to_key_and_observed_bytes(tmp_path: Path) -> None:
    store = _store(tmp_path)
    stored = store.put_verified(io.BytesIO(b"A"))
    final_path = tmp_path / Path(stored.object_key)
    tampered = b"B"
    tampered_sha256 = hashlib.sha256(tampered).hexdigest()
    final_path.chmod(0o644)
    final_path.write_bytes(tampered)
    final_path.chmod(0o444)

    assert not store.verify(stored.object_key, stored.sha256)
    assert not store.verify(stored.object_key, tampered_sha256)
    assert final_path.read_bytes() == tampered


def test_fifo_final_entry_is_rejected_without_blocking(tmp_path: Path) -> None:
    if os.name != "posix" or not hasattr(os, "mkfifo"):
        pytest.skip("FIFO tamper regression requires POSIX mkfifo")
    store = _store(tmp_path)
    stored = store.put_verified(io.BytesIO(CONTENT))
    final_path = tmp_path / Path(stored.object_key)
    final_path.unlink()
    os.mkfifo(final_path)

    def timeout_handler(_signum: int, _frame: object) -> None:
        raise TimeoutError("opening FIFO blocked")

    previous = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(2)
    try:
        with pytest.raises(ObjectIntegrityError, match="regular file"):
            store.open(stored.object_key)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def test_hard_linked_final_entry_is_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path)
    stored = store.put_verified(io.BytesIO(CONTENT))
    final_path = tmp_path / Path(stored.object_key)
    hard_link = final_path.with_name(f"{final_path.name}.link")
    try:
        os.link(final_path, hard_link)
    except OSError as exc:
        pytest.skip(f"hard links unavailable on this filesystem: {exc}")

    with pytest.raises(ObjectIntegrityError, match="hard link"):
        store.open(stored.object_key)


def test_writable_posix_final_entry_is_rejected(tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("POSIX mode contract")
    store = _store(tmp_path)
    stored = store.put_verified(io.BytesIO(CONTENT))
    final_path = tmp_path / Path(stored.object_key)
    final_path.chmod(0o644)

    with pytest.raises(ObjectIntegrityError, match="read-only mode"):
        store.open(stored.object_key)
    with pytest.raises(ObjectIntegrityError, match="read-only mode"):
        store.put_verified(io.BytesIO(CONTENT))


def test_final_file_is_read_only_on_posix(tmp_path: Path) -> None:
    store = _store(tmp_path)
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
        _store(root_file)


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
        _store(linked)


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
        _store(linked_parent / "evidence")


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
        _store(tmp_path)


def test_trusted_volume_fallback_requires_explicit_opt_in(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        LocalObjectStore,
        "_supports_secure_dir_fd",
        property(lambda _self: False),
    )

    with pytest.raises(ObjectStoreConfigurationError, match="trusted-volume fallback"):
        LocalObjectStore(tmp_path)

    fallback = LocalObjectStore(tmp_path, allow_trusted_volume_fallback=True)
    assert fallback.put_verified(io.BytesIO(CONTENT)).sha256 == CONTENT_SHA256


def test_linux_uses_directory_descriptors_for_symlink_safe_operations(tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("secure dir_fd operations are a Linux/POSIX contract")

    assert _store(tmp_path)._supports_secure_dir_fd


def test_promotion_fsyncs_file_then_source_and_destination_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.name != "posix":
        pytest.skip("directory fsync is a POSIX durability contract")
    store = _store(tmp_path)
    events: list[str] = []
    real_fsync = os.fsync
    real_replace = store._replace
    real_directory_fsync = store._fsync_directory

    def record_fsync(descriptor: int) -> None:
        if stat.S_ISREG(os.fstat(descriptor).st_mode):
            events.append("file")
        real_fsync(descriptor)

    def record_replace(*args: object) -> None:
        events.append("rename")
        real_replace(*args)

    def record_directory_fsync(descriptor: int | None, path: Path) -> None:
        events.append(f"directory:{path.relative_to(tmp_path).as_posix()}")
        real_directory_fsync(descriptor, path)

    monkeypatch.setattr(os, "fsync", record_fsync)
    monkeypatch.setattr(store, "_replace", record_replace)
    monkeypatch.setattr(store, "_fsync_directory", record_directory_fsync)

    store.put_verified(io.BytesIO(CONTENT))

    rename_index = events.index("rename")
    assert events[:rename_index].count("file") == 2
    assert events[rename_index : rename_index + 3] == [
        "rename",
        "directory:.staging",
        f"directory:sha256/{CONTENT_SHA256[:2]}/{CONTENT_SHA256[2:4]}",
    ]


def test_failure_unlink_fsyncs_staging_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.name != "posix":
        pytest.skip("directory fsync is a POSIX durability contract")
    store = _store(tmp_path)
    synced: list[str] = []
    real_directory_fsync = store._fsync_directory

    def record_directory_fsync(descriptor: int | None, path: Path) -> None:
        synced.append(path.relative_to(tmp_path).as_posix())
        real_directory_fsync(descriptor, path)

    monkeypatch.setattr(store, "_fsync_directory", record_directory_fsync)

    with pytest.raises(ObjectHashMismatchError):
        store.put_verified(io.BytesIO(CONTENT), expected_sha256="0" * 64)

    assert synced == [".staging"]


def test_destination_fsync_is_attempted_when_source_fsync_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.name != "posix":
        pytest.skip("directory fsync is a POSIX durability contract")
    store = _store(tmp_path)
    synced: list[str] = []
    real_directory_fsync = store._fsync_directory

    def fail_source_fsync(descriptor: int | None, path: Path) -> None:
        relative = path.relative_to(tmp_path).as_posix()
        synced.append(relative)
        if relative == ".staging":
            raise OSError("injected source-directory fsync failure")
        real_directory_fsync(descriptor, path)

    monkeypatch.setattr(store, "_fsync_directory", fail_source_fsync)

    with pytest.raises(OSError, match="source-directory fsync failure"):
        store.put_verified(io.BytesIO(CONTENT))

    assert synced == [
        ".staging",
        f"sha256/{CONTENT_SHA256[:2]}/{CONTENT_SHA256[2:4]}",
    ]
    assert (tmp_path / CONTENT_KEY).read_bytes() == CONTENT


def test_missing_root_hierarchy_fsyncs_each_created_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.name != "posix":
        pytest.skip("directory fsync is a POSIX durability contract")
    root = tmp_path / "level-one" / "level-two" / "evidence"
    synced_directories: list[int] = []
    real_fsync = os.fsync

    def record_fsync(descriptor: int) -> None:
        descriptor_stat = os.fstat(descriptor)
        if stat.S_ISDIR(descriptor_stat.st_mode):
            synced_directories.append(descriptor_stat.st_ino)
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", record_fsync)

    _store(root)

    expected = [
        tmp_path.stat().st_ino,
        (tmp_path / "level-one").stat().st_ino,
        (tmp_path / "level-one" / "level-two").stat().st_ino,
    ]
    positions = [synced_directories.index(inode) for inode in expected]
    assert positions == sorted(positions)


def test_staging_and_final_directories_must_share_root_filesystem(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store._root_device += 1

    with pytest.raises(ObjectStoreConfigurationError, match="share one filesystem"):
        store.put_verified(io.BytesIO(CONTENT))

    assert _staging_entries(tmp_path) == []


def test_expected_digest_must_be_canonical(tmp_path: Path) -> None:
    store = _store(tmp_path)

    with pytest.raises(ObjectKeyError, match="canonical SHA-256"):
        store.put_verified(io.BytesIO(CONTENT), expected_sha256=CONTENT_SHA256.upper())
