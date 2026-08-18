# Plan 03a Task 1 encryption verification

- runtime-only key generation: success
- dependency lock: success
- locked installation: success
- disposable DB migration: success
- focused encryption tests: success
- Ruff: success
- complete Python regression: failure

## Focused test tail

```text
============================= test session starts ==============================
platform linux -- Python 3.12.13, pytest-8.4.2, pluggy-1.6.0 -- /home/runner/work/darknetra/darknetra/.venv/bin/python
cachedir: .pytest_cache
hypothesis profile 'ci' -> database=None, deadline=None, print_blob=True, derandomize=True, suppress_health_check=(HealthCheck.too_slow,)
rootdir: /home/runner/work/darknetra/darknetra
configfile: pyproject.toml
plugins: hypothesis-6.165.10, anyio-4.14.2, asyncio-0.26.0
asyncio: mode=Mode.AUTO, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 7 items

apps/api/tests/unit/test_sensitive_field_encryption.py::test_utf8_round_trip_and_redacted_repr PASSED [ 14%]
apps/api/tests/unit/test_sensitive_field_encryption.py::test_arbitrary_unicode_round_trip PASSED [ 28%]
apps/api/tests/unit/test_sensitive_field_encryption.py::test_same_plaintext_uses_fresh_nonce_and_ciphertext PASSED [ 42%]
apps/api/tests/unit/test_sensitive_field_encryption.py::test_aad_binds_purpose_and_resource PASSED [ 57%]
apps/api/tests/unit/test_sensitive_field_encryption.py::test_tampered_nonce_or_ciphertext_fails_closed PASSED [ 71%]
apps/api/tests/unit/test_sensitive_field_encryption.py::test_blind_index_is_stable_and_purpose_scoped PASSED [ 85%]
apps/api/tests/unit/test_sensitive_field_encryption.py::test_runtime_keys_must_decode_to_exactly_32_bytes PASSED [100%]

============================== 7 passed in 2.69s ===============================
```

## Ruff output

```text
All checks passed!
```

## Regression tail

```text

==================================== ERRORS ====================================
________ ERROR collecting apps/api/tests/unit/test_encrypted_fields.py _________
ImportError while importing test module '/home/runner/work/darknetra/darknetra/apps/api/tests/unit/test_encrypted_fields.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
apps/api/tests/unit/test_encrypted_fields.py:7: in <module>
    from darknetra_api.security.encrypted_fields import (
E   ModuleNotFoundError: No module named 'darknetra_api.security.encrypted_fields'
=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /home/runner/work/darknetra/darknetra/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
ERROR apps/api/tests/unit/test_encrypted_fields.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 warning, 1 error in 1.95s
```
