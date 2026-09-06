"""Provider selection must allow the CLI bundled with the pinned Claude SDK."""

import base64

import pytest

from darknetra.agent.service import select_harness
from darknetra.config import Settings


@pytest.mark.parametrize(
    ("mode", "offline", "key", "requested", "expected"),
    [
        ("auto", False, "SYNTHETIC-not-a-real-key", None, "CLAUDE"),
        ("auto", False, None, None, "OFFLINE"),
        ("auto", True, "SYNTHETIC-not-a-real-key", None, "OFFLINE"),
        ("auto", False, "SYNTHETIC-not-a-real-key", "OFFLINE", "OFFLINE"),
        ("deterministic", False, "SYNTHETIC-not-a-real-key", None, "DETERMINISTIC"),
    ],
)
def test_selection_does_not_require_global_claude_binary(
    monkeypatch, mode, offline, key, requested, expected
):
    monkeypatch.setattr("shutil.which", lambda _: None)
    material = base64.b64encode(b"s" * 32).decode()
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://synthetic",
        jwt_signing_key_b64=material,
        field_key_b64=material,
        harness_mode=mode,
        offline_mode=offline,
        anthropic_api_key=key,
    )
    assert select_harness(settings, requested) == expected
