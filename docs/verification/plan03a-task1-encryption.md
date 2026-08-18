# Plan 03a Task 1 encryption verification

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

============================== 7 passed in 2.31s ===============================
```

## Ruff output

```text
All checks passed!
```

## Regression tail

```text
    def require_jwt_signing_key_b64(self) -> str:
        if not self.jwt_signing_key_b64:
>           raise RuntimeError("DARKNETRA_JWT_SIGNING_KEY_B64 must be configured")
E           RuntimeError: DARKNETRA_JWT_SIGNING_KEY_B64 must be configured

apps/api/darknetra_api/config.py:27: RuntimeError
_______ test_inaccessible_case_and_unknown_case_have_identical_404_shape _______

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_inaccessible_case_and_unknown_case_have_identical_404_shape() -> None:
>       _, case_a, case_b, access = await seed_cross_case_fixture()
                                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

apps/api/tests/integration/test_cross_case_authorization.py:119: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
apps/api/tests/integration/test_cross_case_authorization.py:110: in seed_cross_case_fixture
    signing_key_b64=get_settings().require_jwt_signing_key_b64(),
                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = Settings(environment='development', build_version='dev', database_url='postgresql+psycopg://darknetra:darknetra-plan03...alhost:3000', jwt_signing_key_b64='', field_key_v1_b64='', field_blind_index_key_b64='', field_active_key_version='v1')

    def require_jwt_signing_key_b64(self) -> str:
        if not self.jwt_signing_key_b64:
>           raise RuntimeError("DARKNETRA_JWT_SIGNING_KEY_B64 must be configured")
E           RuntimeError: DARKNETRA_JWT_SIGNING_KEY_B64 must be configured

apps/api/darknetra_api/config.py:27: RuntimeError
=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /home/runner/work/darknetra/darknetra/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED apps/api/tests/integration/test_admin_reads.py::test_user_list_is_authorized_and_strictly_redacted - RuntimeError: DARKNETRA_JWT_SIGNING_KEY_B64 must be configured
FAILED apps/api/tests/integration/test_admin_reads.py::test_role_matrix_is_rendered_from_enforcement_policy_source - RuntimeError: DARKNETRA_JWT_SIGNING_KEY_B64 must be configured
FAILED apps/api/tests/integration/test_admin_reads.py::test_audit_reads_are_paginated_filterable_and_case_scoped - RuntimeError: DARKNETRA_JWT_SIGNING_KEY_B64 must be configured
FAILED apps/api/tests/integration/test_auth_flow.py::test_login_me_refresh_rotation_reuse_detection_and_cookie_security - RuntimeError: DARKNETRA_JWT_SIGNING_KEY_B64 must be configured
FAILED apps/api/tests/integration/test_auth_flow.py::test_wrong_password_and_unknown_user_have_identical_failure_shape_and_lockout - RuntimeError: DARKNETRA_JWT_SIGNING_KEY_B64 must be configured
FAILED apps/api/tests/integration/test_auth_flow.py::test_forced_password_change_and_logout_require_session_bound_csrf - RuntimeError: DARKNETRA_JWT_SIGNING_KEY_B64 must be configured
FAILED apps/api/tests/integration/test_case_lifecycle.py::test_case_create_list_retrieve_update_close_reopen_and_audit - RuntimeError: DARKNETRA_JWT_SIGNING_KEY_B64 must be configured
FAILED apps/api/tests/integration/test_case_lifecycle.py::test_case_routes_mask_inaccessible_cases_as_not_found - RuntimeError: DARKNETRA_JWT_SIGNING_KEY_B64 must be configured
FAILED apps/api/tests/integration/test_case_lifecycle.py::test_audit_failure_rolls_back_case_mutation - RuntimeError: DARKNETRA_JWT_SIGNING_KEY_B64 must be configured
FAILED apps/api/tests/integration/test_case_memberships.py::test_case_owner_can_add_list_update_and_remove_members_with_audit - RuntimeError: DARKNETRA_JWT_SIGNING_KEY_B64 must be configured
FAILED apps/api/tests/integration/test_case_memberships.py::test_admin_can_repair_membership_and_last_case_owner_cannot_be_removed - RuntimeError: DARKNETRA_JWT_SIGNING_KEY_B64 must be configured
FAILED apps/api/tests/integration/test_case_memberships.py::test_inaccessible_membership_case_matches_unknown_case_404 - RuntimeError: DARKNETRA_JWT_SIGNING_KEY_B64 must be configured
FAILED apps/api/tests/integration/test_cross_case_authorization.py::test_inaccessible_case_and_unknown_case_have_identical_404_shape - RuntimeError: DARKNETRA_JWT_SIGNING_KEY_B64 must be configured
13 failed, 52 passed, 1 warning in 7.38s
```
