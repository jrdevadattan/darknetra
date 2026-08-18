# Plan 03a Task 2 encrypted-field helper verification

- runtime-only keys: success
- locked installation: success
- disposable DB migration: success
- focused helper tests: success
- Ruff: failure
- complete Python regression: success

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
collecting ... collected 12 items

apps/api/tests/unit/test_encrypted_fields.py::test_pack_and_unpack_are_explicit_and_round_trip_without_decryption PASSED [  8%]
apps/api/tests/unit/test_encrypted_fields.py::test_unpack_rejects_malformed_envelopes[payload0-required envelope fields] PASSED [ 16%]
apps/api/tests/unit/test_encrypted_fields.py::test_unpack_rejects_malformed_envelopes[payload1-valid base64] PASSED [ 25%]
apps/api/tests/unit/test_encrypted_fields.py::test_unpack_rejects_malformed_envelopes[payload2-12 bytes] PASSED [ 33%]
apps/api/tests/unit/test_encrypted_fields.py::test_unpack_rejects_malformed_envelopes[payload3-at least 16 bytes] PASSED [ 41%]
apps/api/tests/unit/test_encrypted_fields.py::test_redaction_is_kind_specific[email-analyst@example.test-a*****t@example.test] PASSED [ 50%]
apps/api/tests/unit/test_encrypted_fields.py::test_redaction_is_kind_specific[phone-+91 98765 43210-********43210] PASSED [ 58%]
apps/api/tests/unit/test_encrypted_fields.py::test_redaction_is_kind_specific[wallet-bc1qsyntheticwalletvalue123456-bc1qsy\u20263456] PASSED [ 66%]
apps/api/tests/unit/test_encrypted_fields.py::test_redaction_is_kind_specific[onion-syntheticexampleabcdef.onion/path-synthe\u2026abcdef.onion] PASSED [ 75%]
apps/api/tests/unit/test_encrypted_fields.py::test_redaction_is_kind_specific[general-authority reference-\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022] PASSED [ 83%]
apps/api/tests/unit/test_encrypted_fields.py::test_empty_sensitive_value_redacts_to_empty_string PASSED [ 91%]
apps/api/tests/unit/test_encrypted_fields.py::test_ordinary_pydantic_serialization_omits_envelope_internals PASSED [100%]

============================== 12 passed in 0.85s ==============================
```

## Ruff output

```text
I001 [*] Import block is un-sorted or un-formatted
  --> apps/api/tests/unit/test_encrypted_fields.py:1:1
   |
 1 | / import base64
 2 | | from dataclasses import dataclass
 3 | |
 4 | | import pytest
 5 | | from pydantic import BaseModel, ConfigDict
 6 | |
 7 | | from darknetra_api.security.encrypted_fields import (
 8 | |     RedactionKind,
 9 | |     SensitiveEnvelopeError,
10 | |     pack_envelope,
11 | |     redact_sensitive_value,
12 | |     unpack_envelope,
13 | | )
14 | | from darknetra_api.security.encryption import EncryptedValue
   | |____________________________________________________________^
help: Organize imports
   |
4  | import pytest
   - from pydantic import BaseModel, ConfigDict
   -
5  | from darknetra_api.security.encrypted_fields import (
--------------------------------------------------------------------------------
12 | from darknetra_api.security.encryption import EncryptedValue
13 + from pydantic import BaseModel, ConfigDict
14 |
   |

Found 1 error.
[*] 1 fixable with the `--fix` option.
```

## Regression tail

```text
........................................................................ [ 93%]
.....                                                                    [100%]
=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /home/runner/work/darknetra/darknetra/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
77 passed, 1 warning in 8.80s
```
