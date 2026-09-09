from __future__ import annotations

from app.config import get_settings
from app.logging import configure_logging
from celery import Celery

_settings = get_settings()
configure_logging(_settings.log_level, json_output=_settings.env != "development")

celery = Celery(
    "sarathi",
    broker=_settings.redis_url,
    backend=_settings.redis_url,
    include=["worker.tasks"],
)

celery.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_time_limit=_settings.max_runtime_s + 120,
    task_soft_time_limit=_settings.max_runtime_s,
    result_expires=3600 * 24,
    broker_connection_retry_on_startup=True,
)
