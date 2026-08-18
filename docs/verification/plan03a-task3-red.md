# Plan 03a Task 3 RED verification

- preparation: success
- migration: success
- reveal contract: failure
```text
============================= test session starts ==============================
platform linux -- Python 3.12.13, pytest-8.4.2, pluggy-1.6.0 -- /home/runner/work/darknetra/darknetra/.venv/bin/python
cachedir: .pytest_cache
hypothesis profile 'ci' -> database=None, deadline=None, print_blob=True, derandomize=True, suppress_health_check=(HealthCheck.too_slow,)
rootdir: /home/runner/work/darknetra/darknetra
configfile: pyproject.toml
plugins: hypothesis-6.165.10, anyio-4.14.2, asyncio-0.26.0
asyncio: mode=Mode.AUTO, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 0 items / 1 error

==================================== ERRORS ====================================
__ ERROR collecting apps/api/tests/integration/test_sensitive_value_reveal.py __
ImportError while importing test module '/home/runner/work/darknetra/darknetra/apps/api/tests/integration/test_sensitive_value_reveal.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
apps/api/tests/integration/test_sensitive_value_reveal.py:18: in <module>
    from darknetra_api.services.sensitive_values import (
E   ModuleNotFoundError: No module named 'darknetra_api.services.sensitive_values'
=========================== short test summary info ============================
ERROR apps/api/tests/integration/test_sensitive_value_reveal.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
=============================== 1 error in 1.26s ===============================
```
