from celery import Task

from darknetra_api.models.enums import JobStatus


class NonRetryableIngestError(Exception):
    """An ingestion failure that policy says must not be retried."""


class IngestTask(Task):
    """Reusable bounded execution policy for Plan 03 ingestion tasks."""

    abstract = True
    autoretry_for = (Exception,)
    dont_autoretry_for = (NonRetryableIngestError,)
    max_retries = 4
    retry_backoff = 2
    retry_backoff_max = 60
    retry_jitter = True

    @classmethod
    def persistence_after_failure(cls, completed_retries: int) -> tuple[int, JobStatus]:
        if completed_retries < 0:
            raise ValueError("completed retries cannot be negative")
        attempt_count = completed_retries + 1
        status = (
            JobStatus.FAILED
            if completed_retries >= cls.max_retries
            else JobStatus.RETRYING
        )
        return attempt_count, status
