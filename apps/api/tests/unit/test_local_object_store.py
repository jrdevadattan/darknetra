from __future__ import annotations

import hashlib
import io
import os
import tempfile
from pathlib import Path

import pytest
from darknetra_api.storage.base import ObjectDigestMismatch, ObjectKeyError
from darknetra_api.storage.local import LocalObjectStore
from hypothesis import given, settings
from hypothesis import strategies as st


def _expected_key(payload: bytes) -> str:
    digest = hashlib.sha256(payload).hexdigest()
    return f"sha256/{digest[:2]}/{digest[2:4]}/{digest}"


def test_put_verified_uses_deterministic_content_address_and_deduplicates(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    payload = b"synthetic evidence bytes\n"

    first = store.put_verified(io.BytesIO(payload))
    second = store.put_verified(io.BytesIO(payload))

    assert first.object_key == _expected_key(payload)
    assert second.object_key == first.object_key
    assert first.sha256 == hashlib.sha256(payload).hexdigest()
    assert first.size_bytes == len(payload)
    assert second.created is False
    assert first.created is True
    assert (tmp_path / first.object_key).read_bytes() == payload


def test_expected_hash_mismatch_promotes_nothing_and_cleans_staging(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    payload = b"different synthetic evidence"
    wrong = "0" * 64

    with pytest.raises(ObjectDigestMismatch):
        store.put_verified(io.BytesIO(payload), expected_sha256=wrong)

    assert not (tmp_path / _expected_key(payload)).exists()
    staging = tmp_path / ".staging"
    assert list(staging.iterdir()) == []


def test_open_verify_and_key_grammar_are_fail_closed(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    payload = b"authorized fixture"
    stored = store.put_verified(io.BytesIO(payload))

    with store.open(stored.object_key) as handle:
        assert handle.read() == payload
    assert store.verify(stored.object_key, stored.sha256) is True
    assert store.verify(stored.object_key, "f" * 64) is False

    for unsafe in (
        "../outside",
        "/absolute/path",
        "sha256/aa/bb/not-a-digest",
        f"sha256/aa/bb/{'a' * 64}/extra",
        f"sha256/ff/ff/{'a' * 64}",
    ):
        with pytest.raises(ObjectKeyError):
            store.open(unsafe)
        with pytest.raises(ObjectKeyError):
            store.verify(unsafe, "a" * 64)


def test_final_object_is_read_only_where_permissions_are_supported(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    stored = store.put_verified(io.BytesIO(b"immutable original"))
    mode = os.stat(tmp_path / stored.object_key).st_mode & 0o777
    assert mode & 0o222 == 0


@given(payload=st.binary(max_size=128 * 1024))
@settings(max_examples=40, deadline=None)
def test_arbitrary_bytes_round_trip_to_digest_address(payload: bytes) -> None:
    with tempfile.TemporaryDirectory() as directory:
        store = LocalObjectStore(Path(directory))
        stored = store.put_verified(io.BytesIO(payload))

        assert stored.object_key == _expected_key(payload)
        assert stored.sha256 == hashlib.sha256(payload).hexdigest()
        assert stored.size_bytes == len(payload)
        with store.open(stored.object_key) as handle:
            assert handle.read() == payload
        assert store.verify(stored.object_key, stored.sha256) is True
