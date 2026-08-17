# Plan 02 Task 13 verification

RED phase outcomes:

- prepare: success
- fixture safety tests: failure

```text
============================= test session starts ==============================
platform linux -- Python 3.12.13, pytest-8.4.2, pluggy-1.6.0 -- /home/runner/work/darknetra/darknetra/.venv/bin/python
cachedir: .pytest_cache
rootdir: /home/runner/work/darknetra/darknetra
configfile: pyproject.toml
plugins: anyio-4.14.2, asyncio-0.26.0
asyncio: mode=Mode.AUTO, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 3 items

apps/api/tests/unit/test_e2e_fixture_cli.py::test_fixture_cli_refuses_non_test_environment FAILED [ 33%]
apps/api/tests/unit/test_e2e_fixture_cli.py::test_fixture_cli_refuses_non_test_scoped_database FAILED [ 66%]
apps/api/tests/unit/test_e2e_fixture_cli.py::test_fixture_cli_requires_synthetic_credentials_from_environment FAILED [100%]

=================================== FAILURES ===================================
________________ test_fixture_cli_refuses_non_test_environment _________________

    def test_fixture_cli_refuses_non_test_environment() -> None:
        result = run_fixture_cli(
            DARKNETRA_ENVIRONMENT="development",
            DARKNETRA_DATABASE_URL="postgresql+psycopg://user:pass@127.0.0.1:55432/darknetra_e2e_test",
            DARKNETRA_E2E_ANALYST_A_PASSWORD="Synthetic-A-Password-42!",
            DARKNETRA_E2E_ANALYST_B_PASSWORD="Synthetic-B-Password-42!",
            DARKNETRA_E2E_BOOTSTRAP_PASSWORD="Synthetic-Bootstrap-42!",
        )
    
        assert result.returncode != 0
>       assert "DARKNETRA_ENVIRONMENT=test" in result.stderr
E       assert 'DARKNETRA_ENVIRONMENT=test' in "/home/runner/work/darknetra/darknetra/.venv/bin/python: can't open file '/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py': [Errno 2] No such file or directory\n"
E        +  where "/home/runner/work/darknetra/darknetra/.venv/bin/python: can't open file '/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py': [Errno 2] No such file or directory\n" = CompletedProcess(args=['/home/runner/work/darknetra/darknetra/.venv/bin/python', '/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py'], returncode=2, stdout='', stderr="/home/runner/work/darknetra/darknetra/.venv/bin/python: can't open file '/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py': [Errno 2] No such file or directory\n").stderr

apps/api/tests/unit/test_e2e_fixture_cli.py:36: AssertionError
______________ test_fixture_cli_refuses_non_test_scoped_database _______________

    def test_fixture_cli_refuses_non_test_scoped_database() -> None:
        result = run_fixture_cli(
            DARKNETRA_ENVIRONMENT="test",
            DARKNETRA_DATABASE_URL="postgresql+psycopg://user:pass@127.0.0.1:5432/darknetra",
            DARKNETRA_E2E_ANALYST_A_PASSWORD="Synthetic-A-Password-42!",
            DARKNETRA_E2E_ANALYST_B_PASSWORD="Synthetic-B-Password-42!",
            DARKNETRA_E2E_BOOTSTRAP_PASSWORD="Synthetic-Bootstrap-42!",
        )
    
        assert result.returncode != 0
>       assert "test-scoped database" in result.stderr
E       assert 'test-scoped database' in "/home/runner/work/darknetra/darknetra/.venv/bin/python: can't open file '/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py': [Errno 2] No such file or directory\n"
E        +  where "/home/runner/work/darknetra/darknetra/.venv/bin/python: can't open file '/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py': [Errno 2] No such file or directory\n" = CompletedProcess(args=['/home/runner/work/darknetra/darknetra/.venv/bin/python', '/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py'], returncode=2, stdout='', stderr="/home/runner/work/darknetra/darknetra/.venv/bin/python: can't open file '/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py': [Errno 2] No such file or directory\n").stderr

apps/api/tests/unit/test_e2e_fixture_cli.py:49: AssertionError
_______ test_fixture_cli_requires_synthetic_credentials_from_environment _______

    def test_fixture_cli_requires_synthetic_credentials_from_environment() -> None:
        result = run_fixture_cli(
            DARKNETRA_ENVIRONMENT="test",
            DARKNETRA_DATABASE_URL="postgresql+psycopg://user:pass@127.0.0.1:55432/darknetra_e2e_test",
        )
    
        assert result.returncode != 0
>       assert "DARKNETRA_E2E_ANALYST_A_PASSWORD" in result.stderr
E       assert 'DARKNETRA_E2E_ANALYST_A_PASSWORD' in "/home/runner/work/darknetra/darknetra/.venv/bin/python: can't open file '/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py': [Errno 2] No such file or directory\n"
E        +  where "/home/runner/work/darknetra/darknetra/.venv/bin/python: can't open file '/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py': [Errno 2] No such file or directory\n" = CompletedProcess(args=['/home/runner/work/darknetra/darknetra/.venv/bin/python', '/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py'], returncode=2, stdout='', stderr="/home/runner/work/darknetra/darknetra/.venv/bin/python: can't open file '/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py': [Errno 2] No such file or directory\n").stderr

apps/api/tests/unit/test_e2e_fixture_cli.py:59: AssertionError
=========================== short test summary info ============================
FAILED apps/api/tests/unit/test_e2e_fixture_cli.py::test_fixture_cli_refuses_non_test_environment - assert 'DARKNETRA_ENVIRONMENT=test' in "/home/runner/work/darknetra/darknetra/.venv/bin/python: can't open file '/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py': [Errno 2] No such file or directory\n"
 +  where "/home/runner/work/darknetra/darknetra/.venv/bin/python: can't open file '/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py': [Errno 2] No such file or directory\n" = CompletedProcess(args=['/home/runner/work/darknetra/darknetra/.venv/bin/python', '/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py'], returncode=2, stdout='', stderr="/home/runner/work/darknetra/darknetra/.venv/bin/python: can't open file '/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py': [Errno 2] No such file or directory\n").stderr
FAILED apps/api/tests/unit/test_e2e_fixture_cli.py::test_fixture_cli_refuses_non_test_scoped_database - assert 'test-scoped database' in "/home/runner/work/darknetra/darknetra/.venv/bin/python: can't open file '/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py': [Errno 2] No such file or directory\n"
 +  where "/home/runner/work/darknetra/darknetra/.venv/bin/python: can't open file '/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py': [Errno 2] No such file or directory\n" = CompletedProcess(args=['/home/runner/work/darknetra/darknetra/.venv/bin/python', '/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py'], returncode=2, stdout='', stderr="/home/runner/work/darknetra/darknetra/.venv/bin/python: can't open file '/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py': [Errno 2] No such file or directory\n").stderr
FAILED apps/api/tests/unit/test_e2e_fixture_cli.py::test_fixture_cli_requires_synthetic_credentials_from_environment - assert 'DARKNETRA_E2E_ANALYST_A_PASSWORD' in "/home/runner/work/darknetra/darknetra/.venv/bin/python: can't open file '/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py': [Errno 2] No such file or directory\n"
 +  where "/home/runner/work/darknetra/darknetra/.venv/bin/python: can't open file '/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py': [Errno 2] No such file or directory\n" = CompletedProcess(args=['/home/runner/work/darknetra/darknetra/.venv/bin/python', '/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py'], returncode=2, stdout='', stderr="/home/runner/work/darknetra/darknetra/.venv/bin/python: can't open file '/home/runner/work/darknetra/darknetra/scripts/create_e2e_fixture.py': [Errno 2] No such file or directory\n").stderr
============================== 3 failed in 0.08s ===============================
```
