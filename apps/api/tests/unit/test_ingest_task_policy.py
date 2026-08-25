from celery import Celery
from darknetra_api.jobs.base import IngestTask, NonRetryableIngestError
from darknetra_api.models.enums import JobStatus


def test_ingest_task_execution_retries_are_bounded_with_backoff_and_jitter() -> None:
    assert IngestTask.autoretry_for == (Exception,)
    assert IngestTask.dont_autoretry_for == (NonRetryableIngestError,)
    assert IngestTask.max_retries == 4
    assert IngestTask.retry_backoff == 2
    assert IngestTask.retry_backoff_max == 60
    assert IngestTask.retry_jitter is True


def test_ingest_task_maps_attempts_to_authoritative_job_status() -> None:
    assert IngestTask.persistence_after_failure(0) == (1, JobStatus.RETRYING)
    assert IngestTask.persistence_after_failure(3) == (4, JobStatus.RETRYING)
    assert IngestTask.persistence_after_failure(4) == (5, JobStatus.FAILED)


def test_ingest_task_exhausts_after_five_total_attempts() -> None:
    application = Celery("ingest-policy-test", task_cls=IngestTask)
    application.conf.update(task_always_eager=True, task_eager_propagates=False)
    attempts: list[int] = []

    @application.task
    def always_fails() -> None:
        attempts.append(len(attempts) + 1)
        raise RuntimeError("synthetic retryable failure")

    result = always_fails.apply()

    assert result.failed()
    assert attempts == [1, 2, 3, 4, 5]
