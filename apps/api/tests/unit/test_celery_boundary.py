from __future__ import annotations

from darknetra_api.jobs.celery_app import celery_app


def test_celery_boundary_accepts_json_only_and_has_bounded_execution() -> None:
    assert tuple(celery_app.conf.accept_content) == ("json",)
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.result_serializer == "json"
    assert celery_app.conf.task_ignore_result is True
    assert celery_app.conf.task_default_queue == "ingest"
    assert celery_app.conf.task_soft_time_limit == 270
    assert celery_app.conf.task_time_limit == 300
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert celery_app.conf.worker_prefetch_multiplier == 1
