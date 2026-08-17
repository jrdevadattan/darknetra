# Plan 02 Task 13 verification

Deterministic fixture RED phase outcomes:

- prepare: success
- disposable DB migration: success
- fixture safety tests: success
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
    
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
>       assert payload == {
            "users": {
                "analyst_a": {"id": str(ANALYST_A_ID), "username": "e2e.analyst.a"},
                "analyst_b": {"id": str(ANALYST_B_ID), "username": "e2e.analyst.b"},
                "bootstrap": {"id": str(BOOTSTRAP_ID), "username": "e2e.bootstrap"},
            },
            "cases": {
                "analyst_a": {"id": str(CASE_A_ID), "case_code": "E2E-A-001"},
                "analyst_b": {"id": str(CASE_B_ID), "case_code": "E2E-B-001"},
            },
        }
E       AssertionError: assert {'status': 'v...-environment'} == {'cases': {'a....bootstrap'}}}
E         
E         Left contains 1 more item:
E         {'status': 'validated-test-fixture-environment'}
E         Right contains 2 more items:
E         {'cases': {'analyst_a': {'case_code': 'E2E-A-001',
E                                  'id': '00000000-0000-4000-8000-000000000ca1'},
E                    'analyst_b': {'case_code': 'E2E-B-001',
E                                  'id': '00000000-0000-4000-8000-000000000cb1'}},
E          'users': {'analyst_a': {'id': '00000000-0000-4000-8000-0000000000a1',
E                                  'username': 'e2e.analyst.a'},
E                    'analyst_b': {'id': '00000000-0000-4000-8000-0000000000b1',
E                                  'username': 'e2e.analyst.b'},
E                    'bootstrap': {'id': '00000000-0000-4000-8000-0000000000c1',
E                                  'username': 'e2e.bootstrap'}}}
E         
E         Full diff:
E           {
E         +     'status': 'validated-test-fixture-environment',
E         -     'cases': {
E         -         'analyst_a': {
E         -             'case_code': 'E2E-A-001',
E         -             'id': '00000000-0000-4000-8000-000000000ca1',
E         -         },
E         -         'analyst_b': {
E         -             'case_code': 'E2E-B-001',
E         -             'id': '00000000-0000-4000-8000-000000000cb1',
E         -         },
E         -     },
E         -     'users': {
E         -         'analyst_a': {
E         -             'id': '00000000-0000-4000-8000-0000000000a1',
E         -             'username': 'e2e.analyst.a',
E         -         },
E         -         'analyst_b': {
E         -             'id': '00000000-0000-4000-8000-0000000000b1',
E         -             'username': 'e2e.analyst.b',
E         -         },
E         -         'bootstrap': {
E         -             'id': '00000000-0000-4000-8000-0000000000c1',
E         -             'username': 'e2e.bootstrap',
E         -         },
E         -     },
E           }

apps/api/tests/integration/test_e2e_fixture_creation.py:65: AssertionError
=========================== short test summary info ============================
FAILED apps/api/tests/integration/test_e2e_fixture_creation.py::test_fixture_cli_creates_deterministic_isolated_state_without_secret_output - AssertionError: assert {'status': 'v...-environment'} == {'cases': {'a....bootstrap'}}}
  
  Left contains 1 more item:
  {'status': 'validated-test-fixture-environment'}
  Right contains 2 more items:
  {'cases': {'analyst_a': {'case_code': 'E2E-A-001',
                           'id': '00000000-0000-4000-8000-000000000ca1'},
             'analyst_b': {'case_code': 'E2E-B-001',
                           'id': '00000000-0000-4000-8000-000000000cb1'}},
   'users': {'analyst_a': {'id': '00000000-0000-4000-8000-0000000000a1',
                           'username': 'e2e.analyst.a'},
             'analyst_b': {'id': '00000000-0000-4000-8000-0000000000b1',
                           'username': 'e2e.analyst.b'},
             'bootstrap': {'id': '00000000-0000-4000-8000-0000000000c1',
                           'username': 'e2e.bootstrap'}}}
  
  Full diff:
    {
  +     'status': 'validated-test-fixture-environment',
  -     'cases': {
  -         'analyst_a': {
  -             'case_code': 'E2E-A-001',
  -             'id': '00000000-0000-4000-8000-000000000ca1',
  -         },
  -         'analyst_b': {
  -             'case_code': 'E2E-B-001',
  -             'id': '00000000-0000-4000-8000-000000000cb1',
  -         },
  -     },
  -     'users': {
  -         'analyst_a': {
  -             'id': '00000000-0000-4000-8000-0000000000a1',
  -             'username': 'e2e.analyst.a',
  -         },
  -         'analyst_b': {
  -             'id': '00000000-0000-4000-8000-0000000000b1',
  -             'username': 'e2e.analyst.b',
  -         },
  -         'bootstrap': {
  -             'id': '00000000-0000-4000-8000-0000000000c1',
  -             'username': 'e2e.bootstrap',
  -         },
  -     },
    }
============================== 1 failed in 0.39s ===============================
```
