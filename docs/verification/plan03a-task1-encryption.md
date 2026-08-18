# Plan 03a Task 1 encryption verification

- dependency lock: success
- locked installation: success
- focused encryption tests: success
- Ruff: failure
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

============================== 7 passed in 2.48s ===============================
```

## Ruff output

```text
UP035 [*] Import from `collections.abc` instead: `Mapping`
  --> apps/api/darknetra_api/security/encryption.py:9:1
   |
 7 | import os
 8 | from dataclasses import dataclass
 9 | from typing import TYPE_CHECKING, Mapping
   | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
10 |
11 | from cryptography.exceptions import InvalidTag
   |
help: Import from `collections.abc`
   |
8  | from dataclasses import dataclass
   - from typing import TYPE_CHECKING, Mapping
9  + from typing import TYPE_CHECKING
10 + from collections.abc import Mapping
11 |
   |

UP012 [*] Unnecessary UTF-8 `encoding` argument to `encode`
   --> apps/api/darknetra_api/security/encryption.py:127:16
    |
125 |         _validate_context_component(resource_id, name="resource_id", allow_colon=True)
126 |         _validate_context_component(key_version, name="key_version", allow_colon=False)
127 |         return f"darknetra:{purpose}:{resource_id}:{key_version}".encode("utf-8")
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
128 |
129 |     def encrypt(self, plaintext: str, *, purpose: str, resource_id: str) -> EncryptedValue:
    |
help: Remove unnecessary `encoding` argument
    |
126 |         _validate_context_component(key_version, name="key_version", allow_colon=False)
    -         return f"darknetra:{purpose}:{resource_id}:{key_version}".encode("utf-8")
127 +         return f"darknetra:{purpose}:{resource_id}:{key_version}".encode()
128 |
    |

I001 [*] Import block is un-sorted or un-formatted
  --> apps/api/tests/unit/test_sensitive_field_encryption.py:1:1
   |
 1 | / import base64
 2 | |
 3 | | import pytest
 4 | | from hypothesis import given, strategies as st
 5 | |
 6 | | from darknetra_api.security.encryption import (
 7 | |     EncryptedValue,
 8 | |     SensitiveFieldConfigurationError,
 9 | |     SensitiveFieldCrypto,
10 | |     SensitiveFieldDecryptionError,
11 | |     decode_key_b64,
12 | | )
   | |_^
help: Organize imports
   |
3  | import pytest
   - from hypothesis import given, strategies as st
   -
4  | from darknetra_api.security.encryption import (
--------------------------------------------------------------------------------
10 | )
11 + from hypothesis import given
12 + from hypothesis import strategies as st
13 |
   |

Found 3 errors.
[*] 3 fixable with the `--fix` option.
```

## Regression tail

```text
ERROR apps/api/tests/integration/test_case_lifecycle.py::test_case_routes_mask_inaccessible_cases_as_not_found - sqlalchemy.exc.OperationalError: (psycopg.OperationalError) connection failed: connection to server at "127.0.0.1", port 5432 failed: Connection refused
	Is the server running on that host and accepting TCP/IP connections?
(Background on this error at: https://sqlalche.me/e/20/e3q8)
ERROR apps/api/tests/integration/test_case_lifecycle.py::test_audit_failure_rolls_back_case_mutation - sqlalchemy.exc.OperationalError: (psycopg.OperationalError) connection failed: connection to server at "127.0.0.1", port 5432 failed: Connection refused
	Is the server running on that host and accepting TCP/IP connections?
(Background on this error at: https://sqlalche.me/e/20/e3q8)
ERROR apps/api/tests/integration/test_case_memberships.py::test_case_owner_can_add_list_update_and_remove_members_with_audit - sqlalchemy.exc.OperationalError: (psycopg.OperationalError) connection failed: connection to server at "127.0.0.1", port 5432 failed: Connection refused
	Is the server running on that host and accepting TCP/IP connections?
(Background on this error at: https://sqlalche.me/e/20/e3q8)
ERROR apps/api/tests/integration/test_case_memberships.py::test_admin_can_repair_membership_and_last_case_owner_cannot_be_removed - sqlalchemy.exc.OperationalError: (psycopg.OperationalError) connection failed: connection to server at "127.0.0.1", port 5432 failed: Connection refused
	Is the server running on that host and accepting TCP/IP connections?
(Background on this error at: https://sqlalche.me/e/20/e3q8)
ERROR apps/api/tests/integration/test_case_memberships.py::test_inaccessible_membership_case_matches_unknown_case_404 - sqlalchemy.exc.OperationalError: (psycopg.OperationalError) connection failed: connection to server at "127.0.0.1", port 5432 failed: Connection refused
	Is the server running on that host and accepting TCP/IP connections?
(Background on this error at: https://sqlalche.me/e/20/e3q8)
ERROR apps/api/tests/integration/test_cross_case_authorization.py::test_inaccessible_case_and_unknown_case_have_identical_404_shape - sqlalchemy.exc.OperationalError: (psycopg.OperationalError) connection failed: connection to server at "127.0.0.1", port 5432 failed: Connection refused
	Is the server running on that host and accepting TCP/IP connections?
(Background on this error at: https://sqlalche.me/e/20/e3q8)
ERROR apps/api/tests/integration/test_cross_case_authorization.py::test_case_role_cannot_elevate_beyond_global_role - sqlalchemy.exc.OperationalError: (psycopg.OperationalError) connection failed: connection to server at "127.0.0.1", port 5432 failed: Connection refused
	Is the server running on that host and accepting TCP/IP connections?
(Background on this error at: https://sqlalche.me/e/20/e3q8)
ERROR apps/api/tests/integration/test_cross_case_authorization.py::test_admin_can_repair_membership_but_does_not_bypass_case_read_scope - sqlalchemy.exc.OperationalError: (psycopg.OperationalError) connection failed: connection to server at "127.0.0.1", port 5432 failed: Connection refused
	Is the server running on that host and accepting TCP/IP connections?
(Background on this error at: https://sqlalche.me/e/20/e3q8)
ERROR apps/api/tests/integration/test_schema_constraints.py::test_normalized_username_is_unique - sqlalchemy.exc.OperationalError: (psycopg.OperationalError) connection failed: connection to server at "127.0.0.1", port 5432 failed: Connection refused
	Is the server running on that host and accepting TCP/IP connections?
(Background on this error at: https://sqlalche.me/e/20/e3q8)
ERROR apps/api/tests/integration/test_schema_constraints.py::test_disabled_user_flag_is_persisted - sqlalchemy.exc.OperationalError: (psycopg.OperationalError) connection failed: connection to server at "127.0.0.1", port 5432 failed: Connection refused
	Is the server running on that host and accepting TCP/IP connections?
(Background on this error at: https://sqlalche.me/e/20/e3q8)
ERROR apps/api/tests/integration/test_schema_constraints.py::test_case_code_is_unique - sqlalchemy.exc.OperationalError: (psycopg.OperationalError) connection failed: connection to server at "127.0.0.1", port 5432 failed: Connection refused
	Is the server running on that host and accepting TCP/IP connections?
(Background on this error at: https://sqlalche.me/e/20/e3q8)
ERROR apps/api/tests/integration/test_schema_constraints.py::test_case_membership_is_unique_per_user_and_case - sqlalchemy.exc.OperationalError: (psycopg.OperationalError) connection failed: connection to server at "127.0.0.1", port 5432 failed: Connection refused
	Is the server running on that host and accepting TCP/IP connections?
(Background on this error at: https://sqlalche.me/e/20/e3q8)
ERROR apps/api/tests/integration/test_schema_constraints.py::test_audit_events_are_append_only_at_orm_boundary - sqlalchemy.exc.OperationalError: (psycopg.OperationalError) connection failed: connection to server at "127.0.0.1", port 5432 failed: Connection refused
	Is the server running on that host and accepting TCP/IP connections?
(Background on this error at: https://sqlalche.me/e/20/e3q8)
1 failed, 41 passed, 1 skipped, 1 warning, 22 errors in 14.68s
```
