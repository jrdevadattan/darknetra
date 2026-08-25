from celery import Celery
from kombu import Queue

from darknetra_api.config import get_settings

settings = get_settings()
sensitive_field_crypto = settings.require_sensitive_field_crypto()

celery_app = Celery(
    "darknetra",
    broker=settings.redis_url,
    include=["darknetra_api.jobs.tasks"],
)
celery_app.conf.update(
    accept_content=["json"],
    task_serializer="json",
    result_serializer="json",
    task_ignore_result=True,
    task_default_queue="ingest",
    task_queues=(Queue("ingest", routing_key="ingest"),),
    task_default_exchange="darknetra",
    task_default_exchange_type="direct",
    task_default_routing_key="ingest",
    task_soft_time_limit=270,
    task_time_limit=300,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 3600},
    task_publish_retry=True,
    task_publish_retry_policy={
        "max_retries": 5,
        "interval_start": 0,
        "interval_step": 1,
        "interval_max": 5,
    },
    enable_utc=True,
    timezone="UTC",
)
