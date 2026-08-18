# Plan 03a Task 4 key-version verification

- runtime-only keys: success
- locked installation: success
- disposable DB migration: success
- focused keyring tests: success
- Ruff: failure
- complete Python regression: success

## Focused tests
```text
============================= test session starts ==============================
platform linux -- Python 3.12.13, pytest-8.4.2, pluggy-1.6.0 -- /home/runner/work/darknetra/darknetra/.venv/bin/python
cachedir: .pytest_cache
hypothesis profile 'ci' -> database=None, deadline=None, print_blob=True, derandomize=True, suppress_health_check=(HealthCheck.too_slow,)
rootdir: /home/runner/work/darknetra/darknetra
configfile: pyproject.toml
plugins: hypothesis-6.165.10, anyio-4.14.2, asyncio-0.26.0
asyncio: mode=Mode.AUTO, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 5 items

apps/api/tests/unit/test_sensitive_field_keyring.py::test_v1_envelope_remains_decryptable_after_v2_becomes_active PASSED [ 20%]
apps/api/tests/unit/test_sensitive_field_keyring.py::test_reencrypt_uses_active_v2_and_preserves_blind_index PASSED [ 40%]
apps/api/tests/unit/test_sensitive_field_keyring.py::test_unknown_key_version_fails_closed_without_active_key_fallback PASSED [ 60%]
apps/api/tests/unit/test_sensitive_field_keyring.py::test_base64_mapping_builds_versioned_runtime_keyring PASSED [ 80%]
apps/api/tests/unit/test_sensitive_field_keyring.py::test_empty_or_invalid_keyring_fails_closed PASSED [100%]

============================== 5 passed in 0.83s ===============================
```

## Ruff
```text
I001 [*] Import block is un-sorted or un-formatted
  --> apps/api/tests/unit/test_sensitive_field_keyring.py:1:1
   |
 1 | / import base64
 2 | |
 3 | | import pytest
 4 | |
 5 | | from darknetra_api.security.encryption import (
 6 | |     EncryptedValue,
 7 | |     SensitiveFieldConfigurationError,
 8 | |     SensitiveFieldCrypto,
 9 | |     UnknownKeyVersionError,
10 | | )
11 | | from darknetra_api.security.keyring import SensitiveFieldKeyring
   | |________________________________________________________________^
help: Organize imports
  |
3 | import pytest
  -
4 | from darknetra_api.security.encryption import (
  |

Found 1 error.
[*] 1 fixable with the `--fix` option.
```

## Full suite
```text
........................................................................ [ 81%]
................                                                         [100%]
=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /home/runner/work/darknetra/darknetra/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
88 passed, 1 warning in 8.85s
```
