# Plan 02 Task 14 preflight

- prepare: success
- Docker auth configuration contract: failure

```text
.F.                                                                      [100%]
=================================== FAILURES ===================================
_______ test_compose_api_receives_authentication_security_configuration ________

    def test_compose_api_receives_authentication_security_configuration() -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
>       assert "DARKNETRA_WEB_ORIGIN:" in compose
E       AssertionError: assert 'DARKNETRA_WEB_ORIGIN:' in 'name: darknetra\n\nservices:\n  postgres:\n    image: postgres:18\n    environment:\n      POSTGRES_DB: darknetra\n  ...: service_healthy\n    networks:\n      - app\n\nnetworks:\n  app:\n    driver: bridge\n\nvolumes:\n  postgres-data:\n'

tests/repo/test_compose_contract.py:17: AssertionError
=========================== short test summary info ============================
FAILED tests/repo/test_compose_contract.py::test_compose_api_receives_authentication_security_configuration - AssertionError: assert 'DARKNETRA_WEB_ORIGIN:' in 'name: darknetra\n\nservices:\n  postgres:\n    image: postgres:18\n    environment:\n      POSTGRES_DB: darknetra\n  ...: service_healthy\n    networks:\n      - app\n\nnetworks:\n  app:\n    driver: bridge\n\nvolumes:\n  postgres-data:\n'
1 failed, 2 passed in 0.04s
```
