# Plan 03a keyring settings RED verification

- preparation: success
- settings integration test: failure
```text
============================= test session starts ==============================
platform linux -- Python 3.12.13, pytest-8.4.2, pluggy-1.6.0 -- /home/runner/work/darknetra/darknetra/.venv/bin/python
cachedir: .pytest_cache
hypothesis profile 'ci' -> database=None, deadline=None, print_blob=True, derandomize=True, suppress_health_check=(HealthCheck.too_slow,)
rootdir: /home/runner/work/darknetra/darknetra
configfile: pyproject.toml
plugins: hypothesis-6.165.10, anyio-4.14.2, asyncio-0.26.0
asyncio: mode=Mode.AUTO, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 6 items / 5 deselected / 1 selected

apps/api/tests/unit/test_sensitive_field_keyring.py::test_default_crypto_boundary_uses_active_versioned_keyring_from_settings FAILED [100%]

=================================== FAILURES ===================================
___ test_default_crypto_boundary_uses_active_versioned_keyring_from_settings ___

    def test_default_crypto_boundary_uses_active_versioned_keyring_from_settings() -> None:
        settings = Settings(
            field_keyring_b64_json=json.dumps(
                {
                    "v1": base64.b64encode(key(0x11)).decode("ascii"),
                    "v2": base64.b64encode(key(0x22)).decode("ascii"),
                }
            ),
            field_active_key_version="v2",
            field_blind_index_key_b64=base64.b64encode(key(0x33)).decode("ascii"),
        )
    
>       boundary = crypto_from_settings(settings)
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

apps/api/tests/unit/test_sensitive_field_keyring.py:142: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
apps/api/darknetra_api/security/encryption.py:185: in crypto_from_settings
    settings.require_field_key_v1_b64(),
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = Settings(environment='development', build_version='dev', database_url='postgresql+psycopg://darknetra:darknetra-dev-on...IiIiIiIiI="}', field_blind_index_key_b64='MzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzM=', field_active_key_version='v2')

    def require_field_key_v1_b64(self) -> str:
        if not self.field_key_v1_b64:
>           raise RuntimeError("DARKNETRA_FIELD_KEY_V1_B64 must be configured")
E           RuntimeError: DARKNETRA_FIELD_KEY_V1_B64 must be configured

apps/api/darknetra_api/config.py:33: RuntimeError
=========================== short test summary info ============================
FAILED apps/api/tests/unit/test_sensitive_field_keyring.py::test_default_crypto_boundary_uses_active_versioned_keyring_from_settings - RuntimeError: DARKNETRA_FIELD_KEY_V1_B64 must be configured
======================= 1 failed, 5 deselected in 1.14s ========================
```
