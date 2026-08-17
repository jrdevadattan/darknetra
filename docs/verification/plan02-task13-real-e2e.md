# Plan 02 Task 13 verification

Deterministic fixture phase outcomes:

- prepare: success
- disposable DB migration: success
- Ruff fixture code: failure
- fixture safety tests: failure
- fixture integration test: failure

```text
============================= test session starts ==============================
platform linux -- Python 3.12.13, pytest-8.4.2, pluggy-1.6.0 -- /home/runner/work/darknetra/darknetra/.venv/bin/python
cachedir: .pytest_cache
rootdir: /home/runner/work/darknetra/darknetra
configfile: pyproject.toml
plugins: anyio-4.14.2, asyncio-0.26.0
asyncio: mode=Mode.AUTO, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 1 item

apps/api/tests/integration/test_e2e_fixture_creation.py::test_fixture_cli_creates_deterministic_isolated_state_without_secret_output FAILED [100%]

=================================== FAILURES ===================================
_ test_fixture_cli_creates_deterministic_isolated_state_without_secret_output __

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_fixture_cli_creates_deterministic_isolated_state_without_secret_output() -> None:
        database_url = e2e_database_url()
        env = os.environ.copy()
        env.update(
            {
                "DARKNETRA_ENVIRONMENT": "test",
                "DARKNETRA_DATABASE_URL": database_url,
                "DARKNETRA_E2E_ANALYST_A_PASSWORD": ANALYST_A_PASSWORD,
                "DARKNETRA_E2E_ANALYST_B_PASSWORD": ANALYST_B_PASSWORD,
                "DARKNETRA_E2E_BOOTSTRAP_PASSWORD": BOOTSTRAP_PASSWORD,
            }
        )
    
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
    
>       assert result.returncode == 0, result.stderr
E       AssertionError: Traceback (most recent call last):
E           File "/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py", line 14, in <module>
E             from darknetra_api.models.audit import AuditEvent
E         ModuleNotFoundError: No module named 'darknetra_api'
E         
E       assert 1 == 0
E        +  where 1 = CompletedProcess(args=['/home/runner/work/darknetra/darknetra/.venv/bin/python', '/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py'], returncode=1, stdout='', stderr='Traceback (most recent call last):\n  File "/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py", line 14, in <module>\n    from darknetra_api.models.audit import AuditEvent\nModuleNotFoundError: No module named \'darknetra_api\'\n').returncode

apps/api/tests/integration/test_e2e_fixture_creation.py:63: AssertionError
=========================== short test summary info ============================
FAILED apps/api/tests/integration/test_e2e_fixture_creation.py::test_fixture_cli_creates_deterministic_isolated_state_without_secret_output - AssertionError: Traceback (most recent call last):
    File "/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py", line 14, in <module>
      from darknetra_api.models.audit import AuditEvent
  ModuleNotFoundError: No module named 'darknetra_api'
  
assert 1 == 0
 +  where 1 = CompletedProcess(args=['/home/runner/work/darknetra/darknetra/.venv/bin/python', '/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py'], returncode=1, stdout='', stderr='Traceback (most recent call last):\n  File "/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py", line 14, in <module>\n    from darknetra_api.models.audit import AuditEvent\nModuleNotFoundError: No module named \'darknetra_api\'\n').returncode
============================== 1 failed in 0.65s ===============================
```
