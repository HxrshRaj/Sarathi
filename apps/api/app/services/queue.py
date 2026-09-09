"""Thin producer side of the job queue.

The API never imports the worker package; it dispatches tasks by name so the two
deployables stay decoupled. If Celery isn't installed (pure-API image) or the
broker is down, callers get a clear infra error.
"""

from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.errors import AppError, ErrorCategory
from app.logging import get_logger

log = get_logger("queue")

TASK_RUN = "worker.run_agent_task"
TASK_INDEX = "worker.index_repository_version"
TASK_EVALUATION = "worker.run_evaluation"

_app: Any = None


def _celery() -> Any:
    global _app
    if _app is None:
        try:
            from celery import Celery
        except ImportError as exc:  # pragma: no cover
            raise AppError(ErrorCategory.INFRA, "Job queue unavailable in this deployment") from exc
        url = get_settings().redis_url
        _app = Celery("sarathi-producer", broker=url, backend=url)
    return _app


def dispatch(name: str, **kwargs: Any) -> str:
    try:
        result = _celery().send_task(name, kwargs=kwargs)
    except Exception as exc:  # noqa: BLE001
        log.error("dispatch_failed", task=name, error=str(exc))
        raise AppError(
            ErrorCategory.INFRA, "Could not enqueue background job", retryable=True
        ) from exc
    log.info("dispatched", task=name, job_id=result.id)
    return result.id
