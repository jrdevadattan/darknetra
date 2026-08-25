import base64
import importlib
import secrets
import sys

import pytest
from darknetra_api.config import get_settings
from darknetra_api.jobs.base import IngestTask


@pytest.fixture(autouse=True)
def isolated_worker_module():
    get_settings.cache_clear()
    sys.modules.pop("darknetra_api.jobs.celery_app", None)
    try:
        yield
    finally:
        sys.modules.pop("darknetra_api.jobs.celery_app", None)
        get_settings.cache_clear()


def test_celery_uses_json_only_ingest_queue_and_bounded_retries(monkeypatch) -> None:
    monkeypatch.setenv(
        "DARKNETRA_FIELD_KEY_V1_B64",
        base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
    )
    monkeypatch.setenv(
        "DARKNETRA_FIELD_BLIND_INDEX_KEY_B64",
        base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
    )
    get_settings.cache_clear()
    module = importlib.import_module("darknetra_api.jobs.celery_app")
    celery_app = module.celery_app

    assert issubclass(celery_app.Task, IngestTask)
    assert tuple(celery_app.conf.accept_content) == ("json",)
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.result_serializer == "json"
    assert celery_app.conf.task_default_queue == "ingest"
    assert celery_app.conf.task_soft_time_limit == 270
    assert celery_app.conf.task_time_limit == 300
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert celery_app.conf.worker_prefetch_multiplier == 1
    assert celery_app.conf.task_publish_retry is True
    assert celery_app.conf.task_publish_retry_policy == {
        "max_retries": 5,
        "interval_start": 0,
        "interval_step": 1,
        "interval_max": 5,
    }


def test_missing_keys_fail_closed_after_successful_worker_construction(monkeypatch) -> None:
    monkeypatch.setenv(
        "DARKNETRA_FIELD_KEY_V1_B64",
        base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
    )
    monkeypatch.setenv(
        "DARKNETRA_FIELD_BLIND_INDEX_KEY_B64",
        base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
    )
    importlib.import_module("darknetra_api.jobs.celery_app")

    sys.modules.pop("darknetra_api.jobs.celery_app", None)
    get_settings.cache_clear()
    monkeypatch.delenv("DARKNETRA_FIELD_KEY_V1_B64")
    monkeypatch.delenv("DARKNETRA_FIELD_BLIND_INDEX_KEY_B64")

    with pytest.raises(ValueError):
        importlib.import_module("darknetra_api.jobs.celery_app")
