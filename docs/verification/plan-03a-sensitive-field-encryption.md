# Plan 03a — sensitive-field encryption verification

- **Verified commit:** `00efa2e39dd0d5e6e1e8ed3fe13cda334d8e000c`
- **Observed at (UTC):** `2026-08-18T09:06:08Z`
- **Runner:** GitHub Actions `ubuntu-latest`

| Gate | Outcome |
|---|---|
| Runtime-only v1/v2/JWT/blind keys | success |
| README + architecture preflight | success |
| Locked workspace installation | success |
| Disposable PostgreSQL migration | success |
| Active-v2 runtime probe | failure |
| `uv run ruff check .` | success |
| `uv run pytest -q` | failure |
| Authentication/case regression | success |
| Tracked-secret scan | success |
| Docker Compose configuration | success |
| Docker API/web smoke | success |

## Python suite
```text
........................................................................ [ 80%]
...........F.....                                                        [100%]
=================================== FAILURES ===================================
___ test_default_crypto_boundary_uses_active_versioned_keyring_from_settings ___

    def test_default_crypto_boundary_uses_active_versioned_keyring_from_settings() -> None:
        settings = Settings(
            field_keyring_b64_json=json.dumps(
                {
                    "v1": base64.b64encode(key(0x11)).decode("ascii"),
                    "v2": base64.b64encode(key(0x22)).decode("ascii"),
                }
            ),
            field_active_key_version="v2",
            field_blind_index_key_b64=base64.b64encode(key(0x33)).decode("ascii"),
        )
    
        boundary = crypto_from_settings(settings)
        encrypted = boundary.encrypt(
            "versioned setting",
            purpose="evidence.source_locator",
            resource_id="evidence-settings",
        )
    
        assert encrypted.key_version == "v2"
>       assert boundary.key_versions == frozenset({"v1", "v2"})
               ^^^^^^^^^^^^^^^^^^^^^
E       AttributeError: 'SensitiveFieldCrypto' object has no attribute 'key_versions'

apps/api/tests/unit/test_sensitive_field_keyring.py:150: AttributeError
=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /home/runner/work/darknetra/darknetra/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED apps/api/tests/unit/test_sensitive_field_keyring.py::test_default_crypto_boundary_uses_active_versioned_keyring_from_settings - AttributeError: 'SensitiveFieldCrypto' object has no attribute 'key_versions'
1 failed, 88 passed, 1 warning in 9.70s
```

## Authentication and case regression
```text
................                                                         [100%]
16 passed in 2.91s
```

## Secret scan
```text
No committed sensitive-field key literal detected.
```

## Docker smoke
```text

#37 [web] resolving provenance for metadata file
#37 DONE 0.0s
 api  Built
 web  Built
 Network darknetra_app  Creating
 Network darknetra_app  Created
 Volume "darknetra_postgres-data"  Creating
 Volume "darknetra_postgres-data"  Created
 Container darknetra-postgres-1  Creating
 Container darknetra-postgres-1  Created
 Container darknetra-api-1  Creating
 Container darknetra-api-1  Created
 Container darknetra-web-1  Creating
 Container darknetra-web-1  Created
 Container darknetra-postgres-1  Starting
 Container darknetra-postgres-1  Started
 Container darknetra-postgres-1  Waiting
 Container darknetra-postgres-1  Healthy
 Container darknetra-api-1  Starting
 Container darknetra-api-1  Started
 Container darknetra-api-1  Waiting
 Container darknetra-api-1  Healthy
 Container darknetra-web-1  Starting
 Container darknetra-web-1  Started
 Container darknetra-web-1  Waiting
 Container darknetra-postgres-1  Waiting
 Container darknetra-api-1  Waiting
 Container darknetra-postgres-1  Healthy
 Container darknetra-api-1  Healthy
 Container darknetra-web-1  Healthy
NAME                   IMAGE           COMMAND                  SERVICE    CREATED          STATUS                    PORTS
darknetra-api-1        darknetra-api   "uv run --no-sync uv…"   api        12 seconds ago   Up 6 seconds (healthy)    127.0.0.1:8000->8000/tcp
darknetra-postgres-1   postgres:18     "docker-entrypoint.s…"   postgres   12 seconds ago   Up 12 seconds (healthy)   127.0.0.1:5432->5432/tcp
darknetra-web-1        darknetra-web   "docker-entrypoint.s…"   web        12 seconds ago   Up Less than a second     127.0.0.1:3000->3000/tcp
```

## Plan 03 handoff

Evidence Vault must use the versioned envelope, purpose-scoped blind index, explicit redaction and audited reveal boundaries for source locators, authority references and sensitive notes. It must not add auto-decrypting ORM properties or persist runtime keys.
