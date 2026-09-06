"""Seed consumes its declared manifest and retains full relative filename keys."""

import hashlib
import importlib.util
import json
from argparse import Namespace
from pathlib import Path

import httpx


def test_if_missing_retains_manifest_paths_and_recovers_unfinished_upload(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "seed_test", Path(__file__).resolve().parents[2] / "scripts/seed_synthetic_case.py"
    )
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    monkeypatch.setattr(seed, "ROOT", tmp_path)
    monkeypatch.setenv("DARKNETRA_ADMIN_PASSWORD", "SYNTHETIC permanent password")
    monkeypatch.setenv("DARKNETRA_DEMO_ANALYST_PASSWORD", "SYNTHETIC analyst password")
    bundle = tmp_path / "bundle"
    (bundle / "chat").mkdir(parents=True)
    content = b"SYNTHETIC manifest example"
    (bundle / "chat/chat.txt").write_bytes(content)
    sha = hashlib.sha256(content).hexdigest()
    (bundle / "manifest.json").write_text(
        json.dumps(
            {
                "source_class": "SYNTHETIC",
                "files": [
                    {
                        "filename": "chat/chat.txt",
                        "sha256": sha,
                        "source_class": "SYNTHETIC",
                        "source_family": "SYNTHETIC_CHAT_A",
                    }
                ],
            }
        )
    )
    case = {
        "id": "synthetic-case",
        "code": "SYN-CHD-001",
        "title": "SYN-CHD-001 synthetic demo",
        "demo": True,
        "status": "OPEN",
    }
    evidence = {
        "id": "synthetic-evidence",
        "code": "E-0001",
        "sha256": sha,
        "original_filename": "chat.txt",
        "status": "READY",
    }

    def handle(request):
        path = request.url.path
        if path == "/api/v1/auth/login":
            return httpx.Response(
                200,
                json={"must_change_password": False},
                headers={"set-cookie": "darknetra_csrf=synthetic"},
            )
        if path == "/api/v1/users":
            return httpx.Response(200, json={"items": [{"username": "analyst.demo"}]})
        if path == "/api/v1/cases":
            return httpx.Response(200, json={"items": [case]})
        if path == "/api/v1/cases/synthetic-case/evidence":
            return httpx.Response(200, json={"items": [evidence]})
        raise AssertionError(f"Unexpected HTTP request: {request.method} {path}")

    real_client = httpx.Client
    monkeypatch.setattr(
        seed.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    seed.seed(Namespace(bundle=bundle, api="http://synthetic.test", if_missing=True, reset=False))
    result = json.loads((tmp_path / "data/synthetic/out/seed_result.json").read_text())
    assert result["files"] == {"chat/chat.txt": "E-0001"}
