# Plan 03a Task 3 audited reveal verification

- runtime-only keys: success
- locked installation: success
- disposable DB migration: success
- focused reveal/policy tests: success
- Ruff: success
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
collecting ... collected 9 items

apps/api/tests/integration/test_sensitive_value_reveal.py::test_viewer_is_denied_sensitive_reveal_without_audit PASSED [ 11%]
apps/api/tests/integration/test_sensitive_value_reveal.py::test_cross_case_reveal_matches_repository_not_found_policy PASSED [ 22%]
apps/api/tests/integration/test_sensitive_value_reveal.py::test_reveal_reason_must_be_bounded[] PASSED [ 33%]
apps/api/tests/integration/test_sensitive_value_reveal.py::test_reveal_reason_must_be_bounded[short] PASSED [ 44%]
apps/api/tests/integration/test_sensitive_value_reveal.py::test_reveal_reason_must_be_bounded[xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx] PASSED [ 55%]
apps/api/tests/integration/test_sensitive_value_reveal.py::test_authorized_reveal_returns_plaintext_and_audits_only_context PASSED [ 66%]
apps/api/tests/unit/test_policy.py::test_role_permission_map_is_explicit_and_immutable PASSED [ 77%]
apps/api/tests/unit/test_policy.py::test_global_authorization_uses_current_role_state PASSED [ 88%]
apps/api/tests/unit/test_policy.py::test_forced_password_change_blocks_normal_mutations_and_sensitive_reveals PASSED [100%]

============================== 9 passed in 1.49s ===============================
```

## Ruff
```text
All checks passed!
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
88 passed, 1 warning in 9.28s
```
