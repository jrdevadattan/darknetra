# Plan 02 Task 13 verification

Deterministic fixture phase outcomes:

- prepare: success
- disposable DB migration: success
- Ruff fixture code: failure
- fixture safety tests: success
- fixture integration test: success

## Ruff output

```text
I001 [*] Import block is un-sorted or un-formatted
  --> apps/api/tests/integration/test_e2e_fixture_creation.py:1:1
   |
 1 | / import json
 2 | | import os
 3 | | import subprocess
 4 | | import sys
 5 | | from pathlib import Path
 6 | | from uuid import UUID
 7 | |
 8 | | import pytest
 9 | | import sqlalchemy as sa
10 | | from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
11 | |
12 | | from darknetra_api.models.case import Case
13 | | from darknetra_api.models.case_membership import CaseMembership, CaseMembershipRole
14 | | from darknetra_api.models.enums import GlobalRole
15 | | from darknetra_api.models.user import User
16 | | from darknetra_api.security.passwords import verify_password
   | |____________________________________________________________^
17 |
18 |   ROOT = Path(__file__).resolve().parents[4]
   |
help: Organize imports
   |
9  | import sqlalchemy as sa
   - from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
   -
10 | from darknetra_api.models.case import Case
--------------------------------------------------------------------------------
14 | from darknetra_api.security.passwords import verify_password
15 + from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
16 |
   |

ASYNC221 Async functions should not run processes with blocking methods
  --> apps/api/tests/integration/test_e2e_fixture_creation.py:54:14
   |
52 |     )
53 |
54 |     result = subprocess.run(
   |              ^^^^^^^^^^^^^^
55 |         [sys.executable, str(SCRIPT)],
56 |         cwd=ROOT,
   |

BLE001 Do not catch blind exception: `Exception`
   --> scripts/create_e2e_fixture.py:223:12
    |
221 |         print(str(exc), file=sys.stderr)
222 |         return 2
223 |     except Exception as exc:  # pragma: no cover - exercised by workflow diagnostics
    |            ^^^^^^^^^
224 |         print(f"fixture creation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
225 |         return 1
    |

Found 3 errors.
[*] 1 fixable with the `--fix` option.
```

## Fixture integration output

```text
============================= test session starts ==============================
platform linux -- Python 3.12.13, pytest-8.4.2, pluggy-1.6.0 -- /home/runner/work/darknetra/darknetra/.venv/bin/python
cachedir: .pytest_cache
rootdir: /home/runner/work/darknetra/darknetra
configfile: pyproject.toml
plugins: anyio-4.14.2, asyncio-0.26.0
asyncio: mode=Mode.AUTO, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 1 item

apps/api/tests/integration/test_e2e_fixture_creation.py::test_fixture_cli_creates_deterministic_isolated_state_without_secret_output PASSED [100%]

============================== 1 passed in 1.52s ===============================
```
