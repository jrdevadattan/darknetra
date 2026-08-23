# Plan 02 Task 14 preflight

- prepare: success
- local SameSite hostname contract: failure

```text
..F.                                                                     [100%]
=================================== FAILURES ===================================
__________ test_local_example_keeps_browser_and_api_on_the_same_site ___________

    def test_local_example_keeps_browser_and_api_on_the_same_site() -> None:
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        assert "DARKNETRA_WEB_ORIGIN=http://localhost:3000" in example
>       assert "NEXT_PUBLIC_DARKNETRA_API_BASE_URL=http://localhost:8000" in example
E       AssertionError: assert 'NEXT_PUBLIC_DARKNETRA_API_BASE_URL=http://localhost:8000' in '# FastAPI runtime\nDARKNETRA_ENVIRONMENT=development\nDARKNETRA_BUILD_VERSION=dev\nDARKNETRA_WEB_ORIGIN=http://localh...isible API URL — never put secrets in NEXT_PUBLIC_* values\nNEXT_PUBLIC_DARKNETRA_API_BASE_URL=http://127.0.0.1:8000\n'

tests/repo/test_compose_contract.py:25: AssertionError
=========================== short test summary info ============================
FAILED tests/repo/test_compose_contract.py::test_local_example_keeps_browser_and_api_on_the_same_site - AssertionError: assert 'NEXT_PUBLIC_DARKNETRA_API_BASE_URL=http://localhost:8000' in '# FastAPI runtime\nDARKNETRA_ENVIRONMENT=development\nDARKNETRA_BUILD_VERSION=dev\nDARKNETRA_WEB_ORIGIN=http://localh...isible API URL — never put secrets in NEXT_PUBLIC_* values\nNEXT_PUBLIC_DARKNETRA_API_BASE_URL=http://127.0.0.1:8000\n'
1 failed, 3 passed in 0.04s
```
